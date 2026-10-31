"""Parser and validator for TV and Anime episode season/episode detection."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("arrclean.engine.tv_parser")


class TVParser:
    """Utilities for extracting accurate season and episode metadata from filenames and paths."""

    ORDINAL_MAP = {
        "1st": 1, "first": 1,
        "2nd": 2, "second": 2,
        "3rd": 3, "third": 3,
        "4th": 4, "fourth": 4,
        "5th": 5, "fifth": 5,
        "6th": 6, "sixth": 6,
        "7th": 7, "seventh": 7,
        "8th": 8, "eighth": 8,
        "final": 99,
    }

    # Video resolutions and encoding tags to exclude from episode number detection
    VIDEO_TAG_REGEX = re.compile(
        r"\b(2160p|1080p|1080i|720p|576p|480p|x264|x265|hevc|h264|h265|10bit|8bit|aac|ac3|eac3|dts|flac|web-dl|webrip|bluray|remux)\b",
        re.IGNORECASE,
    )
    CRC_TAG_REGEX = re.compile(r"[\[(][0-9a-fA-F]{8}[\])]")

    @classmethod
    def parse_season_episode(
        cls,
        path: str,
        fallback_season: int | None = None,
        fallback_episode: int | None = None,
    ) -> tuple[int | None, int | None, bool]:
        """Extract the true season and episode number from a file path.

        Returns:
            (season, episode, is_explicit)
        """
        p = path.replace("\\", "/").strip()
        filename = os.path.basename(p)
        dirs = p.split("/")[:-1]

        # 1. Standard SxxExx or 1x03 in filename
        m_se = re.search(r"(?:^|[._ -])s(\d{1,2})[._ -]?e(\d{1,3})(?:[._ -]|$)", filename, re.IGNORECASE)
        if m_se:
            return int(m_se.group(1)), int(m_se.group(2)), True

        m_x = re.search(r"(?:^|[._ -])(\d{1,2})x(\d{1,3})(?:[._ -]|$)", filename, re.IGNORECASE)
        if m_x:
            return int(m_x.group(1)), int(m_x.group(2)), True

        # 2. Season parsing (Anime ordinals, Season X, Part X, Cour X, directory hierarchy)
        season: int | None = None
        is_explicit = False

        # Check for anime ordinal season words (e.g., '2nd season', '2nd episode', '2nd - 03')
        m_ord = re.search(
            r"\b(1st|2nd|3rd|4th|5th|6th|7th|8th|first|second|third|fourth|fifth|final)[._ -]*(?:season|cour|part|episode|ep)?\b",
            p,
            re.IGNORECASE,
        )
        if m_ord:
            ord_key = m_ord.group(1).lower()
            if ord_key in cls.ORDINAL_MAP:
                season = cls.ORDINAL_MAP[ord_key]
                is_explicit = True

        # Check for 'season X', 'cour X' in filename or directory
        if season is None:
            m_s = re.search(r"\b(?:season|series|cour)[._ -]*(\d{1,2})\b", p, re.IGNORECASE)
            if m_s:
                season = int(m_s.group(1))
                is_explicit = True

        # Check for 'part X'
        if season is None:
            m_part = re.search(r"\bpart[._ -]*(\d{1,2})\b", p, re.IGNORECASE)
            if m_part:
                season = int(m_part.group(1))
                is_explicit = True

        # Check directory names for Season X, S0X
        if season is None:
            for d in reversed(dirs):
                m_dir_s = re.search(r"^(?:season|series)[._ -]*(\d{1,2})$", d, re.IGNORECASE)
                if m_dir_s:
                    season = int(m_dir_s.group(1))
                    is_explicit = True
                    break
                m_dir_sx = re.search(r"^s(\d{1,2})$", d, re.IGNORECASE)
                if m_dir_sx:
                    season = int(m_dir_sx.group(1))
                    is_explicit = True
                    break

        # 3. Episode parsing
        episode: int | None = None
        m_ep = re.search(r"\b(?:episode|ep)[._ -]*(\d{1,3})\b", filename, re.IGNORECASE)
        if m_ep:
            episode = int(m_ep.group(1))
        else:
            cleaned_fn = cls.VIDEO_TAG_REGEX.sub("", filename)
            cleaned_fn = cls.CRC_TAG_REGEX.sub("", cleaned_fn)
            candidates = re.findall(r"(?:^|[._ -])(\d{1,3})(?:[ ._\[(]|$)", cleaned_fn)
            valid = [
                int(c)
                for c in candidates
                if int(c) not in (1080, 720, 480, 576, 264, 265, 8, 10)
                and not (1950 <= int(c) <= 2035)
            ]
            if valid:
                episode = valid[-1]

        eff_season = season if season is not None else fallback_season
        eff_episode = episode if episode is not None else fallback_episode
        return eff_season, eff_episode, is_explicit

    @classmethod
    def are_candidates_compatible(
        cls, cand_a: dict[str, Any], cand_b: dict[str, Any]
    ) -> bool:
        """Verify that two duplicate candidate records truly represent the same media entity."""
        # 1. Media type mismatch check
        if cand_a.get("media_type") != cand_b.get("media_type"):
            return False

        # Movies are matched via ratingKey / TMDB IDs
        if cand_a.get("media_type") != "episode":
            return True

        path_a = cand_a.get("file_path", "")
        path_b = cand_b.get("file_path", "")

        # 2. Season & Episode metadata check
        season_a = cand_a.get("season")
        season_b = cand_b.get("season")
        if season_a is not None and season_b is not None and season_a != season_b:
            logger.info("Episode candidate mismatch: Season %s vs Season %s", season_a, season_b)
            return False

        ep_a = cand_a.get("episode")
        ep_b = cand_b.get("episode")
        if ep_a is not None and ep_b is not None and ep_a != ep_b:
            logger.info("Episode candidate mismatch: Episode %s vs Episode %s", ep_a, ep_b)
            return False

        # 3. Path-level Season & Episode re-verification
        parsed_s_a, parsed_e_a, _ = cls.parse_season_episode(path_a, fallback_season=season_a, fallback_episode=ep_a)
        parsed_s_b, parsed_e_b, _ = cls.parse_season_episode(path_b, fallback_season=season_b, fallback_episode=ep_b)

        if parsed_s_a is not None and parsed_s_b is not None and parsed_s_a != parsed_s_b:
            logger.info(
                "Episode candidate mismatch via path parsing: Season %s (%s) vs Season %s (%s)",
                parsed_s_a, path_a, parsed_s_b, path_b,
            )
            return False

        if parsed_e_a is not None and parsed_e_b is not None and parsed_e_a != parsed_e_b:
            logger.info(
                "Episode candidate mismatch via path parsing: Episode %s (%s) vs Episode %s (%s)",
                parsed_e_a, path_a, parsed_e_b, path_b,
            )
            return False

        # 4. Duration sanity check: if both durations are available, ensure they don't diverge drastically
        dur_a = cand_a.get("duration_ms") or 0
        dur_b = cand_b.get("duration_ms") or 0
        if dur_a > 0 and dur_b > 0:
            diff_sec = abs(dur_a - dur_b) / 1000.0
            # If duration differs by more than 180 seconds (3 minutes), they cannot be the same episode
            if diff_sec > 180:
                logger.info(
                    "Episode candidate duration divergence: %.1fs difference (%s vs %s)",
                    diff_sec, path_a, path_b,
                )
                return False

        return True
