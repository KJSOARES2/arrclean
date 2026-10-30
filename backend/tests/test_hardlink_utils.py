"""Tests for hardlink detection and safe unlinking utilities."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.engine.hardlink_utils import HardlinkUtils


class TestHardlinkUtils:
    """Hardlink and inode utility tests using filesystem temp files."""

    def test_get_inode_returns_int(self, tmp_path: Path) -> None:
        file_a = tmp_path / "test1.mkv"
        file_a.write_text("dummy video content")
        inode = HardlinkUtils.get_inode(file_a)
        assert isinstance(inode, int)
        assert inode > 0

    def test_is_hardlinked_false_for_regular_file(self, tmp_path: Path) -> None:
        file_a = tmp_path / "regular.mkv"
        file_a.write_text("single copy")
        assert HardlinkUtils.is_hardlinked(file_a) is False
        assert HardlinkUtils.get_link_count(file_a) == 1

    def test_is_hardlinked_true_for_linked_file(self, tmp_path: Path) -> None:
        file_orig = tmp_path / "original.mkv"
        file_orig.write_text("hardlinked data")

        file_link = tmp_path / "link.mkv"
        os.link(file_orig, file_link)

        assert HardlinkUtils.is_hardlinked(file_orig) is True
        assert HardlinkUtils.is_hardlinked(file_link) is True
        assert HardlinkUtils.get_link_count(file_orig) == 2
        assert HardlinkUtils.are_same_file(file_orig, file_link) is True

    def test_are_same_file_false_for_different_files(self, tmp_path: Path) -> None:
        file_a = tmp_path / "file_a.mkv"
        file_b = tmp_path / "file_b.mkv"
        file_a.write_text("content A")
        file_b.write_text("content B")
        assert HardlinkUtils.are_same_file(file_a, file_b) is False

    def test_safe_remove_library_hardlink_keeps_original(self, tmp_path: Path) -> None:
        download_file = tmp_path / "torrent_download.mkv"
        download_file.write_text("movie data")

        library_file = tmp_path / "library_movie.mkv"
        os.link(download_file, library_file)

        # Attempt safe removal on library_file
        res = HardlinkUtils.safe_remove_library_hardlink(library_file)
        assert res["removed"] is True
        assert res["was_hardlink"] is True
        assert res["remaining_links"] == 1

        # Check library file is gone, but torrent download file is still there with content
        assert not library_file.exists()
        assert download_file.exists()
        assert download_file.read_text() == "movie data"

    def test_safe_remove_library_hardlink_refuses_single_link(self, tmp_path: Path) -> None:
        single_file = tmp_path / "single_copy.mkv"
        single_file.write_text("irreplaceable content")

        res = HardlinkUtils.safe_remove_library_hardlink(single_file)
        # Must refuse to remove because link count is 1
        assert res["removed"] is False
        assert "hardlink" in res["error"].lower()
        assert single_file.exists()

    def test_find_hardlinks_in_directory(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "downloads"
        dest_dir = tmp_path / "media"
        source_dir.mkdir()
        dest_dir.mkdir()

        orig = source_dir / "target.mkv"
        orig.write_text("video")

        link1 = dest_dir / "link1.mkv"
        link2 = dest_dir / "link2.mkv"
        unrelated = dest_dir / "unrelated.mkv"

        os.link(orig, link1)
        os.link(orig, link2)
        unrelated.write_text("other")

        found = HardlinkUtils.find_hardlinks_in_directory(orig, dest_dir)
        assert len(found) == 2
        assert str(link1) in found
        assert str(link2) in found
        assert str(unrelated) not in found

    def test_filesystem_info(self, tmp_path: Path) -> None:
        f = tmp_path / "info_test.mkv"
        f.write_text("123456789")
        info = HardlinkUtils.get_filesystem_info(f)
        assert info["size"] == 9
        assert info["nlink"] == 1
        assert "inode" in info
        assert "device" in info

    def test_is_safe_file_path_security(self, tmp_path: Path) -> None:
        # Forbidden system root paths
        assert HardlinkUtils.is_safe_file_path("/") is False
        assert HardlinkUtils.is_safe_file_path("/etc") is False
        assert HardlinkUtils.is_safe_file_path("/bin") is False
        assert HardlinkUtils.is_safe_file_path("/usr") is False
        assert HardlinkUtils.is_safe_file_path("/var") is False

        # Files inside system directories must strictly be rejected
        assert HardlinkUtils.is_safe_file_path("/etc/passwd") is False
        assert HardlinkUtils.is_safe_file_path("/etc/shadow") is False
        assert HardlinkUtils.is_safe_file_path("/bin/sh") is False
        assert HardlinkUtils.is_safe_file_path("/app/backend/app/main.py") is False
        assert HardlinkUtils.is_safe_file_path("/app/data/arrclean.db") is False

        # Legitimate media file in tmp directory
        valid_media = tmp_path / "Movie.2160p.mkv"
        valid_media.write_text("test")
        assert HardlinkUtils.is_safe_file_path(valid_media) is True
