#!/usr/bin/env python3
"""Inject real VLC/ffmpeg/mpg123 packages into the existing runtime initrd."""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import build
from refresh_ui import parse_cpio

ROOT = Path(__file__).resolve().parent
INITRD = ROOT / "out" / "gtos-rootfs.cpio.gz"
MEDIA_ROOTS = ["ffmpeg", "mpg123", "vlc", "apk-tools", "alpine-keys"]


def main() -> int:
    if not INITRD.is_file():
        raise SystemExit(f"missing {INITRD}")
    build.log("inject media engines into initrd")
    branch = build.detect_branch()
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{branch}"
    by_name, providers = build.load_indexes(branch_root)
    base = {p["P"] for p in build.resolve(by_name, providers, build.RUNTIME_PACKAGES)}
    wanted = build.resolve(by_name, providers, MEDIA_ROOTS)
    raw = gzip.open(INITRD, "rb").read()
    tree = parse_cpio(raw)

    missing = []
    for pkg in wanted:
        stamp = f"usr/share/gtos/pkg-stamps/{pkg['P']}"
        if stamp in tree:
            continue
        # already part of the base OS image — don't re-download
        if pkg["P"] in base and f"usr/share/gtos/pkg-stamps/{pkg['P']}" not in tree:
            # still skip re-fetch for base packages unless stamp missing AND file clearly absent
            # Base packages are already in tree from original build.
            continue
        missing.append(pkg)

    # Always ensure media roots themselves get installed if binaries missing
    need_bins = {
        "ffmpeg": "usr/bin/ffmpeg",
        "mpg123": "usr/bin/mpg123",
        "vlc": "usr/bin/vlc",
        "apk-tools": "sbin/apk",
    }
    # alternate paths
    alt_bins = {
        "apk-tools": ["sbin/apk", "usr/sbin/apk", "usr/bin/apk"],
    }
    force_names = set()
    for name, path in need_bins.items():
        alts = alt_bins.get(name, [path])
        if not any(p in tree for p in alts):
            force_names.add(name)
    if force_names:
        # Install everything not already stamped; include base packages that provide missing bins
        missing = []
        for p in wanted:
            stamp = f"usr/share/gtos/pkg-stamps/{p['P']}"
            if stamp in tree:
                continue
            if p["P"] not in base or p["P"] in force_names or p["P"] in ("libapk", "alpine-keys"):
                missing.append(p)
        build.log(f"binaries missing ({', '.join(sorted(force_names))}) — installing {len(missing)} packages")
    else:
        build.log("media/apk binaries already present")
        missing = []
    build.log(f"packages to install now: {len(missing)}")
    if missing:
        kernel_out: list[bytes] = []
        build.install_packages(tree, missing, kernel_out)
        for pkg in missing:
            build.add_node(
                tree,
                f"usr/share/gtos/pkg-stamps/{pkg['P']}",
                build.FsNode("reg", 0o100644, f"{pkg['P']}={pkg['V']}\n".encode()),
            )

    build.write_cpio(tree, INITRD)
    build.log(f"updated {INITRD} ({INITRD.stat().st_size} bytes)")
    for bin_name in ("usr/bin/ffmpeg", "usr/bin/ffplay", "usr/bin/mpg123", "usr/bin/vlc", "usr/bin/cvlc", "sbin/apk", "usr/sbin/apk"):
        build.log(f"  {bin_name}: {'yes' if bin_name in tree else 'NO'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        build.log(f"error: {exc}")
        sys.exit(1)
