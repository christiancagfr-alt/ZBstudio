"""Fail packaging if workstation configuration or credentials enter a release tree."""

from __future__ import annotations

import fnmatch
from pathlib import Path

FORBIDDEN_NAMES = ("settings.json", "google_token.json", "google_client.json", ".env")
FORBIDDEN_PATTERNS = ("client_secret*.json", "*credentials*.json", "*.sqlite3")
FORBIDDEN_PARTS = {".local-security", ".venv", ".pytest_cache", "__pycache__"}


def unsafe_files(root: Path) -> list[Path]:
    root = root.resolve()
    result = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        # These are public Google API discovery schemas shipped by the client
        # library, not OAuth credential files.  Keep this narrow exception so
        # arbitrary user files named "credentials" still block a release.
        discovery_schema = "googleapiclient" in relative.parts and "discovery_cache" in relative.parts and "documents" in relative.parts
        if discovery_schema:
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts) or path.name in FORBIDDEN_NAMES or any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in FORBIDDEN_PATTERNS):
            result.append(relative)
    return result


def assert_safe_release_tree(root: Path) -> None:
    found = unsafe_files(root)
    if found:
        raise RuntimeError("拒绝打包包含本机配置或凭据的文件：" + ", ".join(str(item) for item in found))
