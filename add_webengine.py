#!/usr/bin/env python3
"""Inject Qt WebEngine (GT Browser engine) into the existing runtime initrd and rebuild gt-shell."""

from __future__ import annotations

import gzip
import sys

from build import (
    OUT,
    RUNTIME_PACKAGES,
    FsNode,
    detect_branch,
    install_packages,
    load_indexes,
    resolve,
    write_cpio,
)
from refresh_ui import parse_cpio

ENGINE_PACKAGES = ["qt6-qtwebengine", "qt6-qtwebchannel", "qt6-qtpositioning"]


def main() -> int:
    runtime_path = OUT / "gtos-rootfs.cpio.gz"
    if not runtime_path.is_file():
        raise SystemExit("нет out/gtos-rootfs.cpio.gz — сначала python build.py")

    branch = detect_branch()
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{branch}"
    by_name, providers = load_indexes(branch_root)
    base = {p["P"] for p in resolve(by_name, providers, [p for p in RUNTIME_PACKAGES if p not in ENGINE_PACKAGES])}
    wanted = [p for p in resolve(by_name, providers, ENGINE_PACKAGES) if p["P"] not in base]
    print("inject:", ", ".join(p["P"] for p in wanted))

    tree = parse_cpio(gzip.open(runtime_path, "rb").read())
    install_packages(tree, wanted, [])
    if "usr/lib/qt6/libexec/QtWebEngineProcess" not in tree:
        raise SystemExit("QtWebEngineProcess не попал в образ")
    write_cpio(tree, runtime_path)
    print(f"updated {runtime_path} ({runtime_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
