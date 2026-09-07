from __future__ import annotations

import os
import shutil
from pathlib import Path


class PathEscapeError(ValueError):
    pass


def safe_join(root: Path, rel: str) -> Path:
    rel = (rel or "").lstrip("/")
    if rel.startswith("sessions/") or rel.startswith("shared/") or rel.startswith("skills/"):
        candidate = (root / rel).resolve()
    elif rel in {"", ".", "./"}:
        candidate = root.resolve()
    else:
        candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise PathEscapeError("非法路径")
    return candidate


def dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def list_dir(root: Path, rel: str) -> list[dict]:
    path = safe_join(root, rel)
    if not path.exists():
        return []
    if path.is_file():
        stat = path.stat()
        return [
            {
                "name": path.name,
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "is_dir": False,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        ]
    items = []
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel_path = str(child.relative_to(root)).replace("\\", "/")
        stat = child.stat()
        items.append(
            {
                "name": child.name,
                "path": rel_path,
                "is_dir": child.is_dir(),
                "size": 0 if child.is_dir() else stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )
    return items


def ensure_dir(root: Path, rel: str) -> Path:
    path = safe_join(root, rel)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(root: Path, rel_dir: str, filename: str, stream, max_bytes: int) -> Path:
    dest_dir = ensure_dir(root, rel_dir)
    dest = safe_join(dest_dir, filename)
    written = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                fh.close()
                dest.unlink(missing_ok=True)
                raise ValueError("超过单文件大小限制")
            fh.write(chunk)
    return dest


def remove_path(root: Path, rel: str) -> None:
    path = safe_join(root, rel)
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
