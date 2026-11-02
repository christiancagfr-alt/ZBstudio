"""Safe destination paths and streaming file commits."""
from pathlib import Path
import os
import re


def checked_child(root, *parts):
    root=Path(root).expanduser().resolve()
    target=root.joinpath(*parts)
    if not target.resolve().is_relative_to(root):raise ValueError('目标路径超出下载目录')
    cursor=root
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink():raise ValueError('下载目标不能是符号链接')
    return target


def drive_literal(value):
    return str(value).replace('\\','\\\\').replace("'","\\'")


def valid_drive_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',str(value)):raise ValueError('无效的 Google Drive ID')
    return value


def source_download_folder(root, day, source_id, mode):
    from .domain import safe_component
    if mode=='per_source':
        import hashlib
        if not source_id:raise ValueError('无法确定任务来源，无法安全分开下载')
        label='来源-'+safe_component(source_id[:16],16)+'-'+hashlib.sha256(source_id.encode('utf-8')).hexdigest()[:8]
        return checked_child(root,safe_component(day),label)
    return checked_child(root,safe_component(day))
