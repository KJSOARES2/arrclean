"""Utilities for detecting and managing hardlinks between download and library directories."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("arrclean.engine.hardlink_utils")


class HardlinkUtils:
    """Utilities for inspecting file inodes, link counts, and managing hardlinks."""

    @staticmethod
    def get_inode(file_path: str | Path) -> int:
        """Get the inode number of a file."""
        return os.stat(file_path).st_ino

    @staticmethod
    def is_hardlinked(file_path: str | Path) -> bool:
        """Check if a file has more than one hardlink (st_nlink > 1)."""
        try:
            return os.stat(file_path).st_nlink > 1
        except (FileNotFoundError, PermissionError) as e:
            logger.debug("Could not stat %s: %s", file_path, e)
            return False

    @staticmethod
    def get_link_count(file_path: str | Path) -> int:
        """Get the number of hardlinks referencing the file's inode."""
        try:
            return os.stat(file_path).st_nlink
        except (FileNotFoundError, PermissionError) as e:
            logger.debug("Could not stat %s: %s", file_path, e)
            return 0

    @staticmethod
    def are_same_file(path_a: str | Path, path_b: str | Path) -> bool:
        """Check if two file paths point to the exact same inode."""
        try:
            return os.path.samefile(path_a, path_b)
        except (FileNotFoundError, PermissionError):
            return False

    @staticmethod
    def find_hardlinks_in_directory(file_path: str | Path, search_dir: str | Path) -> list[str]:
        """Find all file paths in search_dir that share the same inode and device as file_path."""
        matches: list[str] = []
        try:
            target_stat = os.stat(file_path)
            target_ino = target_stat.st_ino
            target_dev = target_stat.st_dev
        except (FileNotFoundError, PermissionError) as e:
            logger.warning("Target file cannot be inspected: %s (%s)", file_path, e)
            return matches

        search_path = Path(search_dir)
        if not search_path.exists() or not search_path.is_dir():
            return matches

        for root, _, files in os.walk(search_path):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                try:
                    s = os.stat(full_path)
                    if s.st_ino == target_ino and s.st_dev == target_dev:
                        matches.append(full_path)
                except (FileNotFoundError, PermissionError):
                    continue

        return matches

    @staticmethod
    def is_safe_file_path(file_path: str | Path) -> bool:
        """Verify that a path is safe to delete and does not target system or application directories."""
        try:
            path_str = os.path.abspath(str(file_path))
            real_path = os.path.realpath(path_str)

            # Block root directory
            if real_path in ("/", ""):
                return False

            # Never allow deleting root or critical OS/application directories
            forbidden_prefixes = (
                "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64",
                "/proc", "/root", "/run", "/sbin", "/sys", "/usr", "/var",
                "/app/backend", "/app/frontend", "/app/data",
            )
            for prefix in forbidden_prefixes:
                if real_path == prefix or real_path.startswith(prefix + "/"):
                    return False

            parent = os.path.dirname(real_path)
            if parent == "" or real_path == parent:
                return False

            # Must be a regular file if it exists, never a directory or device node
            if os.path.exists(real_path) and not os.path.isfile(real_path):
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def safe_remove_library_hardlink(library_path: str | Path) -> dict[str, Any]:
        """Safely unlink a library-side hardlink while guaranteeing data remains intact.

        SAFETY CHECKS:
        1. Path safety check (cannot target OS system paths).
        2. File must exist.
        3. File must have st_nlink > 1 (hardlink confirmed).
        4. Only library_path is unlinked.

        Returns a dictionary with status, remaining links, and any error message.
        """
        path_str = str(library_path)
        if not HardlinkUtils.is_safe_file_path(path_str):
            logger.error("Security refusal: path %s is forbidden or unsafe for deletion", path_str)
            return {
                "removed": False,
                "was_hardlink": False,
                "remaining_links": 0,
                "error": f"Path rejected by security policy: {path_str}",
            }

        if not os.path.exists(path_str):
            return {
                "removed": False,
                "was_hardlink": False,
                "remaining_links": 0,
                "error": f"File does not exist: {path_str}",
            }

        try:
            st = os.stat(path_str)
            link_count = st.st_nlink

            if link_count <= 1:
                logger.warning(
                    "Safety refusal: %s is NOT a hardlink (nlink=%d). Refusing to unlink without torrent purge.",
                    path_str,
                    link_count,
                )
                return {
                    "removed": False,
                    "was_hardlink": False,
                    "remaining_links": link_count,
                    "error": "File has only 1 hardlink; unlinking would destroy data before seeding completes.",
                }

            # Safely unlink the library reference
            os.unlink(path_str)
            logger.info(
                "Successfully unlinked library hardlink %s (original had %d links)",
                path_str,
                link_count,
            )

            return {
                "removed": True,
                "was_hardlink": True,
                "remaining_links": link_count - 1,
                "error": None,
            }

        except Exception as e:
            logger.error("Failed to safely remove hardlink %s: %s", path_str, e)
            return {
                "removed": False,
                "was_hardlink": True,
                "remaining_links": 0,
                "error": str(e),
            }

    @staticmethod
    def get_filesystem_info(file_path: str | Path) -> dict[str, Any]:
        """Return filesystem metadata (device, inode, link count, size) for a file."""
        st = os.stat(file_path)
        return {
            "device": st.st_dev,
            "inode": st.st_ino,
            "nlink": st.st_nlink,
            "size": st.st_size,
            "path": str(file_path),
        }

    @staticmethod
    def can_hardlink(path_a: str | Path, path_b: str | Path) -> bool:
        """Check whether path_a and path_b reside on the same filesystem/device."""
        try:
            stat_a = os.stat(path_a if os.path.exists(path_a) else os.path.dirname(path_a))
            stat_b = os.stat(path_b if os.path.exists(path_b) else os.path.dirname(path_b))
            return stat_a.st_dev == stat_b.st_dev
        except Exception:
            return False
