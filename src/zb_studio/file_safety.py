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
