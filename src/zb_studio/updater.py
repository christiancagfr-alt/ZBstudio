"""Verified, user-initiated desktop updates from GitHub Releases."""

from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from platformdirs import user_cache_dir, user_data_dir

from .version import APP_NAME, APP_VERSION, GITHUB_REPOSITORY

MAX_UPDATE_BYTES = 2 * 1024 * 1024 * 1024


def version_key(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value.strip())
    if not match:
        raise ValueError(f"不支持的发布版本：{value}")
    return tuple(int(part) for part in match.group(1).split("."))


def platform_asset_suffix(platform: str | None = None) -> str:
    platform = platform or sys.platform
    if platform == "win32":
        return "Windows-Setup.exe"
    if platform == "darwin":
        return "macOS.dmg"
    if platform.startswith("linux"):
        return "Linux.tar.gz"
    raise RuntimeError(f"暂不支持在 {platform} 自动更新")


def _https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("更新地址必须是 HTTPS")
    return url


def check_for_update(timeout: float = 15) -> dict:
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
    response = httpx.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"}, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    release = response.json()
    if not isinstance(release, dict) or not isinstance(release.get("tag_name"), str):
        raise ValueError("更新服务返回的数据无效")
    latest = release["tag_name"]
    available = version_key(latest) > version_key(APP_VERSION)
    suffix = platform_asset_suffix()
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    installer = next((asset for asset in assets if isinstance(asset, dict) and str(asset.get("name", "")).endswith(suffix)), None)
    checksums = next((asset for asset in assets if isinstance(asset, dict) and str(asset.get("name", "")).endswith("SHA256SUMS.txt")), None)
    return {"current": APP_VERSION, "latest": latest, "available": available, "release_url": release.get("html_url", ""), "installer": installer, "checksums": checksums}


def _download(url: str, destination: Path, progress) -> Path:
    _https(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    received = 0
    with httpx.stream("GET", url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}, timeout=60, follow_redirects=True) as response:
        response.raise_for_status()
        _https(str(response.url))
        size = int(response.headers.get("content-length", "0") or 0)
        if size > MAX_UPDATE_BYTES:
            raise ValueError("更新包超过允许大小")
        with temporary.open("wb") as output:
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > MAX_UPDATE_BYTES:
                    raise ValueError("更新包超过允许大小")
                output.write(chunk)
                progress(f"正在下载更新：{received // 1024 // 1024} MB" + (f" / {size // 1024 // 1024} MB" if size else ""))
    temporary.replace(destination)
    return destination


def _expected_digest(manifest: Path, filename: str) -> str:
    for line in manifest.read_text("utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and Path(parts[1].lstrip(" *")).name == filename and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0]):
            return parts[0].lower()
    raise ValueError("更新校验清单中没有当前平台安装包")


def _verify(path: Path, expected: str) -> None:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest.lower() != expected.lower():
        path.unlink(missing_ok=True)
        raise ValueError("更新包校验失败，已删除下载文件")


def download_update(info: dict, progress=lambda _: None) -> Path:
    installer, checksums = info.get("installer"), info.get("checksums")
    if not isinstance(installer, dict) or not isinstance(checksums, dict):
        raise ValueError("该发布缺少当前系统安装包或 SHA-256 校验清单")
    for asset in (installer, checksums):
        if not isinstance(asset.get("name"), str) or not isinstance(asset.get("browser_download_url"), str):
            raise ValueError("发布附件信息不完整")
    folder = Path(user_cache_dir(APP_NAME)) / "updates" / str(info["latest"]).lstrip("v")
    manifest = _download(checksums["browser_download_url"], folder / checksums["name"], progress)
    package = _download(installer["browser_download_url"], folder / installer["name"], progress)
    _verify(package, _expected_digest(manifest, package.name))
    progress("更新包下载并校验完成")
    return package


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        root = destination.resolve()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(root) or member.issym() or member.islnk():
                raise ValueError("更新包包含不安全的文件路径")
        tar.extractall(destination, filter="data")


def install_update(package: Path) -> str:
    """Start platform installer only after the package hash was verified."""
    if sys.platform == "win32":
        # Inno Setup asks the Restart Manager to close this verified old app
        # before replacing its files; the GUI exits immediately after launch.
        os.startfile(str(package), "open", "/CLOSEAPPLICATIONS")  # noqa: S606 - verified local installer; user initiated
        return "Windows 安装程序已启动，请按安装向导完成更新。"
    if sys.platform == "darwin":
        with subprocess.Popen(["hdiutil", "attach", "-plist", "-nobrowse", "-readonly", str(package)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) as mount:
            stdout, stderr = mount.communicate(timeout=60)
        if mount.returncode:
            raise RuntimeError(stderr.decode("utf-8", "replace") or "无法挂载 macOS 更新包")
        info = plistlib.loads(stdout)
        mount_point = next((Path(item["mount-point"]) for item in info.get("system-entities", []) if item.get("mount-point")), None)
        if not mount_point:
            raise RuntimeError("无法确定 macOS 更新包挂载位置")
        app = next(mount_point.glob("*.app"), None)
        if not app:
            raise RuntimeError("macOS 更新包中没有应用程序")
        destination = Path.home() / "Applications" / app.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(app, destination, symlinks=True)
        subprocess.run(["hdiutil", "detach", str(mount_point)], check=False, capture_output=True, timeout=60)
        subprocess.Popen(["open", str(destination)])
        return f"已安装到 {destination} 并启动新版本。"
    if sys.platform.startswith("linux"):
        version = package.parent.name
        destination = Path(user_data_dir(APP_NAME)) / "updates" / version
        shutil.rmtree(destination, ignore_errors=True)
        destination.mkdir(parents=True, exist_ok=True)
        _safe_extract(package, destination)
        executable = next((p for p in destination.rglob("ZBStudio") if p.is_file() and os.access(p, os.X_OK)), None)
        if not executable:
            raise RuntimeError("Linux 更新包中没有可执行程序")
        subprocess.Popen([str(executable)], start_new_session=True)
        return f"已安装到 {destination} 并启动新版本。"
    raise RuntimeError("当前系统暂不支持自动安装")
