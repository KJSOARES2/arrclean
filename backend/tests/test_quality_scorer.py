"""Unit tests for the Quality Scoring Engine."""

from __future__ import annotations

import pytest

from app.engine.quality_scorer import (
    AudioCodec,
    HDRFormat,
    MediaQualityInfo,
    QualityScorer,
    QualityWeights,
    Resolution,
    SourceType,
    VideoCodec,
)


class TestScoreCalculation:
    """Tests for composite score calculations."""

    def test_4k_remux_scores_highest(
        self, quality_scorer: QualityScorer, sample_4k_remux: MediaQualityInfo, sample_1080p_webdl: MediaQualityInfo
    ) -> None:
        score_4k = quality_scorer.calculate_composite_score(sample_4k_remux)
        score_1080 = quality_scorer.calculate_composite_score(sample_1080p_webdl)
        assert score_4k > score_1080

    def test_720p_hdtv_scores_lowest(
        self, quality_scorer: QualityScorer, sample_720p_hdtv: MediaQualityInfo, sample_1080p_webdl: MediaQualityInfo
    ) -> None:
        score_720 = quality_scorer.calculate_composite_score(sample_720p_hdtv)
        score_1080 = quality_scorer.calculate_composite_score(sample_1080p_webdl)
        assert score_720 < score_1080

    def test_custom_format_score_boosts_total(self, quality_scorer: QualityScorer) -> None:
        info_without_cf = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.AAC,
            video_codec=VideoCodec.H264,
            custom_format_score=0,
        )
        info_with_cf = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.AAC,
            video_codec=VideoCodec.H264,
            custom_format_score=5000,
        )
        assert quality_scorer.calculate_composite_score(info_with_cf) > quality_scorer.calculate_composite_score(info_without_cf)

    def test_resolution_hierarchy(self, quality_scorer: QualityScorer) -> None:
        scores = []
        for res in [Resolution.SD, Resolution.HD_720P, Resolution.HD_1080P, Resolution.UHD_4K]:
            info = MediaQualityInfo(
                resolution=res,
                hdr_format=HDRFormat.SDR,
                source_type=SourceType.WEB_DL,
                audio_codec=AudioCodec.AAC,
                video_codec=VideoCodec.H264,
            )
            scores.append(quality_scorer.calculate_composite_score(info))

        assert scores[0] < scores[1] < scores[2] < scores[3]

    def test_hdr_hierarchy(self, quality_scorer: QualityScorer) -> None:
        scores = []
        for hdr in [HDRFormat.SDR, HDRFormat.HDR10, HDRFormat.HDR10_PLUS, HDRFormat.DOLBY_VISION]:
            info = MediaQualityInfo(
                resolution=Resolution.UHD_4K,
                hdr_format=hdr,
                source_type=SourceType.WEB_DL,
                audio_codec=AudioCodec.AAC,
                video_codec=VideoCodec.H265,
            )
            scores.append(quality_scorer.calculate_composite_score(info))

        assert scores[0] < scores[1] < scores[2] < scores[3]


class TestComparisonLogic:
    """Tests for pairwise file comparisons."""

    def test_4k_remux_beats_1080p_webdl(
        self, quality_scorer: QualityScorer, sample_4k_remux: MediaQualityInfo, sample_1080p_webdl: MediaQualityInfo
    ) -> None:
        result = quality_scorer.compare(sample_4k_remux, sample_1080p_webdl)
        assert result > 0

    def test_4k_hdr_beats_4k_sdr(
        self, quality_scorer: QualityScorer, sample_4k_remux: MediaQualityInfo, sample_4k_sdr: MediaQualityInfo
    ) -> None:
        result = quality_scorer.compare(sample_4k_remux, sample_4k_sdr)
        assert result > 0

    def test_remux_beats_bluray_same_resolution(self, quality_scorer: QualityScorer) -> None:
        remux = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.REMUX,
            audio_codec=AudioCodec.DTS_HD_MA,
            video_codec=VideoCodec.H264,
        )
        bluray = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.BLURAY,
            audio_codec=AudioCodec.DTS_HD_MA,
            video_codec=VideoCodec.H264,
        )
        assert quality_scorer.compare(remux, bluray) > 0

    def test_truehd_atmos_beats_eac3(self, quality_scorer: QualityScorer) -> None:
        atmos = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.TRUEHD_ATMOS,
            video_codec=VideoCodec.H264,
        )
        eac3 = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.EAC3,
            video_codec=VideoCodec.H264,
        )
        assert quality_scorer.compare(atmos, eac3) > 0

    def test_higher_bitrate_wins_tie(self, quality_scorer: QualityScorer) -> None:
        high_bitrate = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.AAC,
            video_codec=VideoCodec.H264,
            video_bitrate_kbps=12000,
        )
        low_bitrate = MediaQualityInfo(
            resolution=Resolution.HD_1080P,
            hdr_format=HDRFormat.SDR,
            source_type=SourceType.WEB_DL,
            audio_codec=AudioCodec.AAC,
            video_codec=VideoCodec.H264,
            video_bitrate_kbps=4000,
        )
        assert quality_scorer.compare(high_bitrate, low_bitrate) > 0

    def test_equal_files_return_zero(self, quality_scorer: QualityScorer, sample_1080p_webdl: MediaQualityInfo) -> None:
        assert quality_scorer.compare(sample_1080p_webdl, sample_1080p_webdl) == 0


class TestWinnerSelection:
    """Tests for multi-candidate winner selection."""

    def test_select_winner_from_three(
        self,
        quality_scorer: QualityScorer,
        sample_4k_remux: MediaQualityInfo,
        sample_1080p_webdl: MediaQualityInfo,
        sample_720p_hdtv: MediaQualityInfo,
    ) -> None:
        candidates = [sample_720p_hdtv, sample_4k_remux, sample_1080p_webdl]
        winner_idx, loser_indices = quality_scorer.select_winner(candidates)
        assert winner_idx == 1  # 4K Remux
        assert set(loser_indices) == {0, 2}

    def test_select_winner_single_file(
        self, quality_scorer: QualityScorer, sample_1080p_webdl: MediaQualityInfo
    ) -> None:
        winner_idx, loser_indices = quality_scorer.select_winner([sample_1080p_webdl])
        assert winner_idx == 0
        assert loser_indices == []


class TestStringParsing:
    """Tests for robust parser extraction."""

    def test_parse_resolution(self) -> None:
        assert QualityScorer.parse_resolution("2160p") == Resolution.UHD_4K
        assert QualityScorer.parse_resolution("4k") == Resolution.UHD_4K
        assert QualityScorer.parse_resolution("1080p") == Resolution.HD_1080P
        assert QualityScorer.parse_resolution("720p") == Resolution.HD_720P
        assert QualityScorer.parse_resolution("480p") == Resolution.SD

    def test_parse_hdr_format(self) -> None:
        assert QualityScorer.parse_hdr_format("Dolby Vision") == HDRFormat.DOLBY_VISION
        assert QualityScorer.parse_hdr_format("DV") == HDRFormat.DOLBY_VISION
        assert QualityScorer.parse_hdr_format("HDR10+") == HDRFormat.HDR10_PLUS
        assert QualityScorer.parse_hdr_format("HDR10") == HDRFormat.HDR10
        assert QualityScorer.parse_hdr_format("HDR") == HDRFormat.HDR10
        assert QualityScorer.parse_hdr_format("SDR") == HDRFormat.SDR

    def test_parse_source_type(self) -> None:
        assert QualityScorer.parse_source_type("Movie.Remux.mkv") == SourceType.REMUX
        assert QualityScorer.parse_source_type("Movie.BluRay.x264.mkv") == SourceType.BLURAY
        assert QualityScorer.parse_source_type("Movie.WEB-DL.mkv") == SourceType.WEB_DL
        assert QualityScorer.parse_source_type("Movie.HDTV.mkv") == SourceType.HDTV

    def test_parse_audio_codec(self) -> None:
        assert QualityScorer.parse_audio_codec("TrueHD Atmos") == AudioCodec.TRUEHD_ATMOS
        assert QualityScorer.parse_audio_codec("DTS-HD MA") == AudioCodec.DTS_HD_MA
        assert QualityScorer.parse_audio_codec("EAC3 Atmos") == AudioCodec.EAC3_ATMOS
        assert QualityScorer.parse_audio_codec("AC3") == AudioCodec.AC3
        assert QualityScorer.parse_audio_codec("AAC") == AudioCodec.AAC

    def test_parse_video_codec(self) -> None:
        assert QualityScorer.parse_video_codec("HEVC") == VideoCodec.H265
        assert QualityScorer.parse_video_codec("H.265") == VideoCodec.H265
        assert QualityScorer.parse_video_codec("x264") == VideoCodec.H264
        assert QualityScorer.parse_video_codec("AV1") == VideoCodec.AV1

    def test_parse_edition(self) -> None:
        assert QualityScorer.parse_edition("Alien.Directors.Cut.1979.mkv") == "Directors Cut"
        assert QualityScorer.parse_edition("Movie.Extended.Edition.mkv") == "Extended Edition"
        assert QualityScorer.parse_edition("Movie.Theatrical.mkv") == "Theatrical"
        assert QualityScorer.parse_edition("Movie.2160p.mkv") == ""
