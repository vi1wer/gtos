#!/usr/bin/env python3
"""Pack a developer source tree into out/GTOS-source.zip (no ISO / initrd / cache)."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
DEST = OUT / "GTOS-source.zip"

INCLUDE_DIRS = (
    "qml",
    "src",
    "scripts",
    "assets",
    "website/templates",
    "website/static",
    "website/data",
    ".cursor/rules",
)
INCLUDE_FILES = (
    "build.py",
    "run.py",
    "refresh_ui.py",
    "make_iso.py",
    "ship.py",
    "pack_source.py",
    "website/app.py",
)

SKIP_SUFFIX = {".pyc", ".iso", ".qcow2", ".cpio", ".gz", ".partial"}
SKIP_NAMES = {"__pycache__", "node_modules", ".git", "community.db"}


def want(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return False
    if path.suffix.lower() in SKIP_SUFFIX:
        return False
    if path.name.endswith(".cpio.gz"):
        return False
    return True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".zip.partial")
    if tmp.exists():
        tmp.unlink()
    count = 0
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in INCLUDE_FILES:
            src = ROOT / rel
            if src.is_file() and want(src):
                zf.write(src, f"GTOS/{rel.replace(chr(92), '/')}")
                count += 1
        for folder in INCLUDE_DIRS:
            base = ROOT / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or not want(path):
                    continue
                if any(p in SKIP_NAMES for p in path.parts):
                    continue
                arc = "GTOS/" + path.relative_to(ROOT).as_posix()
                zf.write(path, arc)
                count += 1
        readme = (
            "GT/OS — исходники для сборки и QEMU\n"
            "====================================\n\n"
            "Нужны: Python 3, QEMU (qemu-system-x86_64), сеть при первой сборке.\n\n"
            "  python build.py\n"
            "  python run.py\n\n"
            "UI-правка без полной пересборки: python refresh_ui.py\n"
            "ISO: python make_iso.py --version 1.5.1\n"
            "Сайт: cd website && python app.py  →  http://127.0.0.1:5050\n"
        )
        zf.writestr("GTOS/README.txt", readme)
    if DEST.exists():
        DEST.unlink()
    tmp.replace(DEST)
    mb = DEST.stat().st_size / (1024 * 1024)
    print(f"wrote {DEST} ({count} files, {mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
