"""Quality scoring engine for media file comparison.

This is the CORE logic of ArrClean. It defines enumerations for every
quality axis (resolution, HDR, source type, audio/video codec), a
composite scoring formula, and robust parser methods that handle the
messy strings found in real-world filenames and metadata.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("arrclean.engine.quality_scorer")


# ---------------------------------------------------------------------------
# Quality attribute enumerations
# ---------------------------------------------------------------------------

class Resolution(IntEnum):
    """Video resolution tiers ordered from lowest to highest quality."""
    SD = 0
    HD_720P = 1
    HD_1080P = 2
    UHD_4K = 3


class HDRFormat(IntEnum):
    """HDR format tiers ordered from lowest to highest quality."""
    SDR = 0
    HDR10 = 1
    HDR10_PLUS = 2
    DOLBY_VISION = 3
    DOLBY_VISION_HDR10_PLUS = 4


class SourceType(IntEnum):
    """Media source type tiers ordered from lowest to highest quality."""
    UNKNOWN = 0
    HDTV = 1
    WEBIP = 2
    WEBRIP = 2
    WEB_DL = 3
    BLURAY = 4
    REMUX = 5


class AudioCodec(IntEnum):
    """Audio codec tiers ordered from lowest to highest quality."""
    UNKNOWN = 0
    AAC = 1
    MP3 = 2
    AC3 = 3       # DD 5.1
    EAC3 = 4      # DD+
    EAC3_ATMOS = 5  # DD+ Atmos
    DTS = 6
    DTS_HD_MA = 7
    TRUEHD = 8
    TRUEHD_ATMOS = 9
    DTS_X = 10


class VideoCodec(IntEnum):
    """Video codec tiers ordered from lowest to highest quality."""
    UNKNOWN = 0
    MPEG2 = 1
    H264 = 2
    H265 = 3
    AV1 = 4


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class QualityWeights:
    """Configurable weights for quality scoring components."""
    resolution: float = 1.0
    hdr: float = 1.0
    source: float = 1.0
    audio: float = 1.0
    codec: float = 1.0
    bitrate: float = 0.5  # lower weight – acts as a tiebreaker


@dataclass
class MediaQualityInfo:
    """Parsed quality attributes of a media file."""
    resolution: Resolution = Resolution.SD
    hdr_format: HDRFormat = HDRFormat.SDR
    source_type: SourceType = SourceType.UNKNOWN
    audio_codec: AudioCodec = AudioCodec.UNKNOWN
    video_codec: VideoCodec = VideoCodec.UNKNOWN
    video_bitrate_kbps: int = 0
    custom_format_score: int | None = None
    quality_profile_rank: int | None = None
    edition: str = ""
    file_size_bytes: int = 0


# ---------------------------------------------------------------------------
# Edition patterns
# ---------------------------------------------------------------------------

_EDITION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"director'?s?[\s._]*cut", re.IGNORECASE), "Directors Cut"),
    (re.compile(r"theatrical[\s._]*(cut|edition)?", re.IGNORECASE), "Theatrical"),
    (re.compile(r"extended[\s._]*(edition|cut)?", re.IGNORECASE), "Extended Edition"),
    (re.compile(r"unrated[\s._]*(cut|edition)?", re.IGNORECASE), "Unrated"),
    (re.compile(r"ultimate[\s._]*(cut|edition)?", re.IGNORECASE), "Ultimate"),
    (re.compile(r"criterion[\s._]*(collection|edition)?", re.IGNORECASE), "Criterion"),
    (re.compile(r"special[\s._]*edition", re.IGNORECASE), "Special Edition"),
    (re.compile(r"collector'?s?[\s._]*edition", re.IGNORECASE), "Collector's Edition"),
    (re.compile(r"imax[\s._]*(edition)?", re.IGNORECASE), "IMAX"),
    (re.compile(r"remastered", re.IGNORECASE), "Remastered"),
    (re.compile(r"redux", re.IGNORECASE), "Redux"),
    (re.compile(r"final[\s._]*cut", re.IGNORECASE), "Final Cut"),
    (re.compile(r"anniversary[\s._]*(edition)?", re.IGNORECASE), "Anniversary Edition"),
    (re.compile(r"open[\s._]*matte", re.IGNORECASE), "Open Matte"),
    (re.compile(r"black[\s._]*and[\s._]*chrome", re.IGNORECASE), "Black and Chrome"),
    (re.compile(r"hybrid", re.IGNORECASE), "Hybrid"),
]


# ---------------------------------------------------------------------------
# QualityScorer
# ---------------------------------------------------------------------------

class QualityScorer:
    """Scores and compares media files to determine the highest quality version.

    The scorer combines multiple quality axes into a single composite score,
    optionally weighting *arr custom-format scores when available.
    """

    def __init__(self, weights: QualityWeights | None = None) -> None:
        self.weights = weights or QualityWeights()

    # -- Composite scoring ---------------------------------------------------

    def calculate_composite_score(self, info: MediaQualityInfo) -> float:
        """Calculate a composite quality score from all attributes.

        If ``custom_format_score`` is available from Radarr/Sonarr it gets
        **primary** weight (roughly 50 % of the total).  Stream-level
        attributes fill the remainder.

        The score is **not** normalised – typical range is 0–1000+.
        """
        score: float = 0.0

        # 1. Custom format score (from *arr apps) – dominant signal
        if info.custom_format_score is not None:
            score += info.custom_format_score * 5.0

        # 2. Resolution component (max: 3 * 100 * weight = 300)
        score += info.resolution.value * 100.0 * self.weights.resolution

        # 3. HDR component (max: 4 * 50 * weight = 200)
        score += info.hdr_format.value * 50.0 * self.weights.hdr

        # 4. Source type component (max: 5 * 40 * weight = 200)
        score += info.source_type.value * 40.0 * self.weights.source

        # 5. Audio codec component (max: 10 * 20 * weight = 200)
        score += info.audio_codec.value * 20.0 * self.weights.audio

        # 6. Video codec component (max: 4 * 30 * weight = 120)
        score += info.video_codec.value * 30.0 * self.weights.codec

        # 7. Bitrate component (capped at 50, acts as tiebreaker)
        if info.video_bitrate_kbps > 0:
            bitrate_component = min(info.video_bitrate_kbps / 100.0, 50.0)
            score += bitrate_component * self.weights.bitrate

        return round(score, 2)

    # -- Comparison helpers --------------------------------------------------

    def compare(self, file_a: MediaQualityInfo, file_b: MediaQualityInfo) -> int:
        """Compare two media files by composite quality score.

        Returns
        -------
        int
            Positive if *file_a* is higher quality (keep A), negative if
            *file_b* is higher quality (keep B), zero if equal.
        """
        score_a = self.calculate_composite_score(file_a)
        score_b = self.calculate_composite_score(file_b)
        diff = score_a - score_b

        if abs(diff) < 0.01:
            return 0
        return 1 if diff > 0 else -1

    def select_winner(
        self, candidates: list[MediaQualityInfo]
    ) -> tuple[int, list[int]]:
        """Select the highest-quality candidate from a list.

        Parameters
        ----------
        candidates:
            List of :class:`MediaQualityInfo` instances to compare.

        Returns
        -------
        tuple[int, list[int]]
            ``(winner_index, loser_indices)``

        Raises
        ------
        ValueError
            If the candidate list has fewer than two entries.
        """
        if not candidates:
            raise ValueError("Candidate list cannot be empty")
        if len(candidates) == 1:
            return 0, []

        scores = [
            (idx, self.calculate_composite_score(c)) for idx, c in enumerate(candidates)
        ]
        # Sort descending by score; first is the winner
        scores.sort(key=lambda t: t[1], reverse=True)

        winner_idx = scores[0][0]
        loser_indices = [idx for idx, _ in scores[1:]]

        logger.debug(
            "Winner: idx=%d (score=%.2f) | Losers: %s",
            winner_idx,
            scores[0][1],
            [(idx, f"{s:.2f}") for idx, s in scores[1:]],
        )
        return winner_idx, loser_indices

    # -- Static parse methods ------------------------------------------------

    @staticmethod
    def parse_resolution(resolution_str: str) -> Resolution:
        """Parse a resolution string into a :class:`Resolution` enum.

        Handles formats such as ``'2160p'``, ``'4K'``, ``'UHD'``,
        ``'1080p'``, ``'1080i'``, ``'720p'``, ``'480p'``, ``'SD'``, etc.
        """
        if not resolution_str:
            return Resolution.SD

        s = resolution_str.strip().lower()

        if any(tok in s for tok in ("2160", "4k", "uhd")):
            return Resolution.UHD_4K
        if "1080" in s:
            return Resolution.HD_1080P
        if "720" in s:
            return Resolution.HD_720P
        # Fallback – anything with a number below 720
        match = re.search(r"(\d+)", s)
        if match:
            height = int(match.group(1))
            if height >= 2000:
                return Resolution.UHD_4K
            if height >= 900:
                return Resolution.HD_1080P
            if height >= 600:
                return Resolution.HD_720P
        return Resolution.SD

    @staticmethod
    def parse_hdr_format(hdr_str: str) -> HDRFormat:
        """Parse an HDR format string into :class:`HDRFormat`.

        Handles many real-world variations: ``'Dolby Vision'``,
        ``'DV HDR10+'``, ``'HDR10+'``, ``'HDR10'``, ``'HDR'``,
        ``'HLG'``, ``'PQ'``, ``'SDR'``, mixed-case, etc.
        """
        if not hdr_str:
            return HDRFormat.SDR

        s = hdr_str.strip().lower().replace("-", " ").replace("_", " ")

        has_dv = bool(re.search(r"\b(dolby\s*vision|dovi|dv)\b", s)) or "dolby vision" in s or s == "dv"
        has_hdr10_plus = any(tok in s for tok in ("hdr10+", "hdr10 plus", "hdr10plus", "st 2094", "st2094", "hdr10 +"))
        has_hdr10 = "hdr10" in s.replace("+", "") or "hdr 10" in s

        if has_dv and has_hdr10_plus:
            return HDRFormat.DOLBY_VISION_HDR10_PLUS
        if has_dv:
            return HDRFormat.DOLBY_VISION
        if has_hdr10_plus:
            return HDRFormat.HDR10_PLUS
        if has_hdr10 or "hdr" in s or "pq" in s or "hlg" in s or "smpte2084" in s:
            return HDRFormat.HDR10
        return HDRFormat.SDR

    @staticmethod
    def parse_source_type(source_str: str) -> SourceType:
        """Parse a source type string into :class:`SourceType`.

        Handles: ``'Remux'``, ``'BluRay'``, ``'Blu-ray'``, ``'BDRip'``,
        ``'WEB-DL'``, ``'WEBDL'``, ``'WEBRip'``, ``'WEB'``, ``'HDTV'``,
        ``'DVDRip'``, etc.
        """
        if not source_str:
            return SourceType.UNKNOWN

        s = source_str.strip().lower().replace("-", "").replace("_", "").replace(" ", "")

        if "remux" in s:
            return SourceType.REMUX
        if any(tok in s for tok in ("bluray", "bdremux", "bdrip", "brrip", "blu")):
            return SourceType.BLURAY
        if "webdl" in s:
            return SourceType.WEB_DL
        if any(tok in s for tok in ("webrip", "webip")):
            return SourceType.WEBIP
        if s == "web":
            return SourceType.WEB_DL  # generic "WEB" usually means WEB-DL
        if any(tok in s for tok in ("hdtv", "pdtv", "dsr", "dvbrip")):
            return SourceType.HDTV
        if any(tok in s for tok in ("dvdrip", "dvd")):
            return SourceType.HDTV  # DVD quality roughly ≈ HDTV tier
        return SourceType.UNKNOWN

    @staticmethod
    def parse_audio_codec(codec_str: str) -> AudioCodec:
        """Parse an audio codec string into :class:`AudioCodec`.

        Handles variations like ``'TrueHD Atmos'``, ``'Dolby TrueHD'``,
        ``'DTS-HD MA'``, ``'DTS:X'``, ``'EAC3 Atmos'``, ``'DD+ Atmos'``,
        ``'DD 5.1'``, ``'AAC 2.0'``, ``'FLAC'``, ``'MP3'``, etc.
        """
        if not codec_str:
            return AudioCodec.UNKNOWN

        s = codec_str.strip().lower().replace("-", " ").replace("_", " ").replace(":", " ")

        has_atmos = "atmos" in s

        # DTS:X / DTS-X
        if "dts" in s and ("x" in s.split("dts")[-1][:4] or "dts x" in s):
            # Disambiguate DTS-X from DTS-HD. Only match 'dts x' or 'dts:x' pattern,
            # not 'dts-hd' accidentally.
            remainder = s.split("dts")[-1].strip()
            if remainder.startswith("x") or remainder.startswith(" x"):
                return AudioCodec.DTS_X

        # TrueHD (with or without Atmos)
        if "truehd" in s or "true hd" in s:
            return AudioCodec.TRUEHD_ATMOS if has_atmos else AudioCodec.TRUEHD

        # DTS-HD MA
        if "dts" in s and ("hd ma" in s or "hdma" in s or "hd.ma" in s.replace(" ", ".")):
            return AudioCodec.DTS_HD_MA

        # EAC3 / DD+ (with or without Atmos)
        if any(tok in s for tok in ("eac3", "e ac3", "dd+", "ddplus", "dd plus", "dolby digital plus")):
            return AudioCodec.EAC3_ATMOS if has_atmos else AudioCodec.EAC3

        # DTS (generic, after ruling out DTS-HD MA and DTS:X)
        if "dts" in s:
            return AudioCodec.DTS

        # AC3 / DD 5.1
        if any(tok in s for tok in ("ac3", "ac 3", "dd5", "dd 5", "dolby digital", "dd")):
            return AudioCodec.AC3

        # AAC / FLAC (FLAC is roughly AAC tier for scoring purposes)
        if any(tok in s for tok in ("aac", "flac")):
            return AudioCodec.AAC

        # MP3
        if "mp3" in s:
            return AudioCodec.MP3

        return AudioCodec.UNKNOWN

    @staticmethod
    def parse_video_codec(codec_str: str) -> VideoCodec:
        """Parse a video codec string into :class:`VideoCodec`.

        Handles: ``'HEVC'``, ``'H.265'``, ``'x265'``, ``'H.264'``,
        ``'x264'``, ``'AVC'``, ``'AV1'``, ``'MPEG2'``, ``'MPEG-2'``,
        ``'VC-1'``, etc.
        """
        if not codec_str:
            return VideoCodec.UNKNOWN

        s = codec_str.strip().lower().replace("-", "").replace("_", "").replace(".", "").replace(" ", "")

        # AV1 (check before "264"/"265" patterns since "av1" is short)
        if s in ("av1", "av01", "svtav1", "aomav1"):
            return VideoCodec.AV1

        # H.265 / HEVC / x265
        if any(tok in s for tok in ("h265", "x265", "hevc")):
            return VideoCodec.H265

        # H.264 / AVC / x264
        if any(tok in s for tok in ("h264", "x264", "avc")):
            return VideoCodec.H264

        # MPEG-2
        if any(tok in s for tok in ("mpeg2", "mpeg 2", "vc1")):
            return VideoCodec.MPEG2

        return VideoCodec.UNKNOWN

    @staticmethod
    def parse_edition(filename: str) -> str:
        """Extract an edition label from a filename.

        Returns the normalised edition string (e.g. ``"Director's Cut"``,
        ``"Extended"``, ``"Theatrical"``), or an empty string if no edition
        is detected.
        """
        if not filename:
            return ""

        for pattern, label in _EDITION_PATTERNS:
            if pattern.search(filename):
                return label
        return ""
