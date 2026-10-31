"""Tests for TV and anime episode parsing and duplicate validation."""

import pytest
from app.engine.tv_parser import TVParser


def test_standard_tv_parsing():
    s, e, explicit = TVParser.parse_season_episode(
        "/media/tv/Breaking Bad/Season 01/Breaking Bad - S01E03 - 720p.mkv"
    )
    assert s == 1
    assert e == 3
    assert explicit is True

    s2, e2, explicit2 = TVParser.parse_season_episode("show.name.02x05.mkv")
    assert s2 == 2
    assert e2 == 5
    assert explicit2 is True


def test_anime_ordinal_seasons_apothecary_diaries():
    """Test the exact user scenario: S01E03 vs '2nd Episode 3'."""
    s1, e1, exp1 = TVParser.parse_season_episode(
        "/media/anime/The Apothecary Diaries/Season 01/The Apothecary Diaries - S01E03.mkv"
    )
    assert s1 == 1
    assert e1 == 3

    s2, e2, exp2 = TVParser.parse_season_episode(
        "/media/anime/The Apothecary Diaries 2nd Season/The Apothecary Diaries 2nd Episode 3.mkv"
    )
    assert s2 == 2
    assert e2 == 3

    s3, e3, exp3 = TVParser.parse_season_episode(
        "The Apothecary Diaries 2nd Season - 03 [1080p].mkv"
    )
    assert s3 == 2
    assert e3 == 3

    # Candidate compatibility check
    cand_s1 = {
        "media_type": "episode",
        "title": "The Apothecary Diaries S01E03",
        "season": s1,
        "episode": e1,
        "file_path": "/media/anime/The Apothecary Diaries/Season 01/The Apothecary Diaries - S01E03.mkv",
    }
    cand_s2 = {
        "media_type": "episode",
        "title": "The Apothecary Diaries 2nd Episode 3",
        "season": s2,
        "episode": e2,
        "file_path": "/media/anime/The Apothecary Diaries 2nd Season/The Apothecary Diaries 2nd Episode 3.mkv",
    }

    # Must NOT be compatible (Season 1 != Season 2)
    assert TVParser.are_candidates_compatible(cand_s1, cand_s2) is False


def test_anime_subs_please_vs_erai_raws():
    cand_s1 = {
        "media_type": "episode",
        "title": "Kusuriya no Hitorigoto 03",
        "season": 1,
        "episode": 3,
        "file_path": "/media/anime/Kusuriya no Hitorigoto/Season 1/[SubsPlease] Kusuriya no Hitorigoto - 03 (1080p).mkv",
    }
    cand_s2 = {
        "media_type": "episode",
        "title": "Kusuriya no Hitorigoto 2nd Season 03",
        "season": 1,  # Suppose Plex falsely labeled both as Season 1
        "episode": 3,
        "file_path": "/media/anime/Kusuriya no Hitorigoto 2nd Season/[SubsPlease] Kusuriya no Hitorigoto 2nd Season - 03 (1080p).mkv",
    }

    # Even if Plex metadata says season 1, path-level parsing catches the '2nd Season' tag!
    assert TVParser.are_candidates_compatible(cand_s1, cand_s2) is False


def test_genuine_duplicates_allowed():
    cand1 = {
        "media_type": "episode",
        "title": "The Apothecary Diaries S01E03",
        "season": 1,
        "episode": 3,
        "duration_ms": 1420000,
        "file_path": "/media/anime/The Apothecary Diaries/The Apothecary Diaries - S01E03 [720p].mkv",
    }
    cand2 = {
        "media_type": "episode",
        "title": "The Apothecary Diaries S01E03",
        "season": 1,
        "episode": 3,
        "duration_ms": 1422000,  # 2 second difference
        "file_path": "/media/anime/The Apothecary Diaries/The Apothecary Diaries - S01E03 [1080p].mkv",
    }

    assert TVParser.are_candidates_compatible(cand1, cand2) is True


def test_duration_divergence_rejected():
    cand1 = {
        "media_type": "episode",
        "season": 1,
        "episode": 3,
        "duration_ms": 1420000,  # 23m40s
        "file_path": "/media/anime/Show/Show - S01E03.mkv",
    }
    cand2 = {
        "media_type": "episode",
        "season": 1,
        "episode": 3,
        "duration_ms": 2800000,  # ~46m (e.g. double episode or recap or different show)
        "file_path": "/media/anime/Show/Show - S01E03 - Special.mkv",
    }

    assert TVParser.are_candidates_compatible(cand1, cand2) is False
