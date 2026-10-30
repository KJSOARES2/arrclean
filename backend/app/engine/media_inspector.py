"""Media inspection service using ffprobe and mediainfo to inspect stream attributes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

logger = logging.getLogger("arrclean.engine.media_inspector")


class MediaInspector:
    """Inspects video and audio stream attributes directly from media files on disk."""

    def __init__(self) -> None:
        self.ffprobe_path = shutil.which("ffprobe")
        self.mediainfo_path = shutil.which("mediainfo")

    @property
    def has_ffprobe(self) -> bool:
        return self.ffprobe_path is not None

    @property
    def has_mediainfo(self) -> bool:
        return self.mediainfo_path is not None

    async def inspect_file(self, file_path: str) -> dict[str, Any]:
        """Inspect a media file using ffprobe and/or mediainfo.

        Returns a dictionary with parsed stream details (resolution, HDR format,
        codecs, bitrates).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Media file not found: {file_path}")

        file_size = os.path.getsize(file_path)

        mediainfo_data: dict[str, Any] | None = None
        ffprobe_data: dict[str, Any] | None = None

        if self.has_mediainfo:
            try:
                mediainfo_data = await self._run_mediainfo(file_path)
            except Exception as e:
                logger.debug("MediaInfo extraction failed on %s: %s", file_path, e)

        if self.has_ffprobe:
            try:
                ffprobe_data = await self._run_ffprobe(file_path)
            except Exception as e:
                logger.debug("ffprobe extraction failed on %s: %s", file_path, e)

        return self._synthesize_metadata(file_path, file_size, ffprobe_data, mediainfo_data)

    async def _run_ffprobe(self, file_path: str) -> dict[str, Any]:
        """Run ffprobe with JSON output."""
        cmd = [
            self.ffprobe_path or "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe failed ({proc.returncode}): {stderr.decode(errors='ignore')}")

        return json.loads(stdout.decode(errors="ignore"))

    async def _run_mediainfo(self, file_path: str) -> dict[str, Any]:
        """Run mediainfo with JSON output."""
        cmd = [
            self.mediainfo_path or "mediainfo",
            "--Output=JSON",
            file_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"mediainfo failed ({proc.returncode}): {stderr.decode(errors='ignore')}")

        return json.loads(stdout.decode(errors="ignore"))

    def _synthesize_metadata(
        self,
        file_path: str,
        file_size: int,
        ffprobe_data: dict[str, Any] | None,
        mediainfo_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Combine data from ffprobe, mediainfo, or fallback to file stat."""
        video_info: dict[str, Any] = {
            "codec": "unknown",
            "width": 0,
            "height": 0,
            "resolution": "SD",
            "bitrate_kbps": 0,
            "hdr_format": "SDR",
            "bit_depth": 8,
            "frame_rate": 0.0,
        }
        audio_tracks: list[dict[str, Any]] = []
        duration = 0.0

        # Parse MediaInfo if present (usually higher fidelity for HDR & audio profiles)
        if mediainfo_data and "media" in mediainfo_data:
            tracks = mediainfo_data.get("media", {}).get("track", [])
            for track in tracks:
                t_type = track.get("@type", "").lower()
                if t_type == "general":
                    duration = float(track.get("Duration", 0))
                elif t_type == "video" and video_info["codec"] == "unknown":
                    video_info["codec"] = track.get("Format", "").lower()
                    video_info["width"] = int(track.get("Width", 0))
                    video_info["height"] = int(track.get("Height", 0))
                    video_info["bitrate_kbps"] = int(track.get("BitRate", 0)) // 1000
                    video_info["bit_depth"] = int(track.get("BitDepth", 8))
                    hdr_fmt = track.get("HDR_Format", "")
                    hdr_commercial = track.get("HDR_Format_Commercial", "")
                    video_info["hdr_format"] = self._detect_hdr_string(f"{hdr_fmt} {hdr_commercial}")
                elif t_type == "audio":
                    format_str = track.get("Format", "")
                    commercial = track.get("Format_Commercial", "")
                    title = track.get("Title", "")
                    audio_tracks.append({
                        "codec": self._detect_audio_string(f"{format_str} {commercial} {title}"),
                        "channels": int(track.get("Channels", 2)),
                        "language": track.get("Language", "und"),
                        "title": title,
                        "bitrate_kbps": int(track.get("BitRate", 0)) // 1000,
                        "is_default": track.get("Default", "No") == "Yes",
                    })

        # Augment / fallback with ffprobe
        if ffprobe_data:
            fmt = ffprobe_data.get("format", {})
            if duration == 0:
                duration = float(fmt.get("duration", 0))
            if video_info["bitrate_kbps"] == 0 and fmt.get("bit_rate"):
                video_info["bitrate_kbps"] = int(fmt["bit_rate"]) // 1000

            for stream in ffprobe_data.get("streams", []):
                s_type = stream.get("codec_type")
                if s_type == "video" and (video_info["width"] == 0 or video_info["resolution"] == "SD"):
                    video_info["codec"] = stream.get("codec_name", video_info["codec"])
                    video_info["width"] = int(stream.get("width", video_info["width"]))
                    video_info["height"] = int(stream.get("height", video_info["height"]))
                    if video_info["hdr_format"] == "SDR":
                        video_info["hdr_format"] = self._detect_hdr_from_ffprobe_stream(stream)

                elif s_type == "audio" and not audio_tracks:
                    c_name = stream.get("codec_name", "")
                    tags = stream.get("tags", {})
                    title = tags.get("title", "")
                    audio_tracks.append({
                        "codec": self._detect_audio_string(f"{c_name} {title}"),
                        "channels": int(stream.get("channels", 2)),
                        "language": tags.get("language", "und"),
                        "title": title,
                        "bitrate_kbps": int(stream.get("bit_rate", 0)) // 1000 if stream.get("bit_rate") else 0,
                        "is_default": stream.get("disposition", {}).get("default", 0) == 1,
                    })

        # Calculate resolution category from dimensions
        video_info["resolution"] = self._resolution_from_dimensions(video_info["width"], video_info["height"])

        return {
            "file_path": file_path,
            "file_size_bytes": file_size,
            "duration_seconds": duration,
            "video": video_info,
            "audio_tracks": audio_tracks,
        }

    def _resolution_from_dimensions(self, width: int, height: int) -> str:
        """Convert pixel dimensions into resolution labels."""
        if width >= 3800 or height >= 2000:
            return "2160p"
        if width >= 1900 or height >= 900:
            return "1080p"
        if width >= 1200 or height >= 600:
            return "720p"
        return "SD"

    def _detect_hdr_string(self, text: str) -> str:
        """Parse HDR type from descriptive string."""
        s = text.lower()
        if "dolby vision" in s and ("hdr10+" in s or "smpte st 2094" in s):
            return "Dolby Vision / HDR10+"
        if "dolby vision" in s or "dv" in s:
            return "Dolby Vision"
        if "hdr10+" in s or "smpte st 2094" in s:
            return "HDR10+"
        if "hdr10" in s or "hdr" in s or "smpte 2084" in s or "bt.2020" in s or "hlg" in s:
            return "HDR10"
        return "SDR"

    def _detect_hdr_from_ffprobe_stream(self, stream: dict[str, Any]) -> str:
        """Detect HDR attributes from an ffprobe video stream dict."""
        side_data = stream.get("side_data_list", [])
        for entry in side_data:
            s_type = str(entry.get("side_data_type", "")).lower()
            if "dovi" in s_type or "dolby vision" in s_type:
                return "Dolby Vision"
            if "hdr dynamic" in s_type or "smpte 2094" in s_type:
                return "HDR10+"

        transfer = stream.get("color_transfer", "").lower()
        primaries = stream.get("color_primaries", "").lower()

        if transfer in ("smpte2084", "arib-std-b67") or primaries in ("bt2020", "bt2020nc"):
            return "HDR10"

        return "SDR"

    def _detect_audio_string(self, text: str) -> str:
        """Detect audio codec from combined format / title string."""
        s = text.lower()
        if "truehd" in s and "atmos" in s:
            return "TrueHD Atmos"
        if "truehd" in s:
            return "TrueHD"
        if "dts:x" in s or "dts-x" in s:
            return "DTS:X"
        if "dts-hd ma" in s or "dts-hd" in s or "dts-ma" in s or "dtshd" in s:
            return "DTS-HD MA"
        if "eac3" in s and "atmos" in s:
            return "EAC3 Atmos"
        if "eac3" in s or "ddp" in s or "e-ac-3" in s or "enhanced ac-3" in s:
            return "EAC3"
        if "dts" in s:
            return "DTS"
        if "ac3" in s or "ac-3" in s or "dolby digital" in s:
            return "AC3"
        if "aac" in s:
            return "AAC"
        if "flac" in s:
            return "FLAC"
        if "mp3" in s:
            return "MP3"
        return "Unknown"
