#!/usr/bin/env python3
"""Скачать ubuntu-base + .deb для Electron/Cursor (offline glibc-слой)."""

from __future__ import annotations

import gzip
import io
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
BASE_NAME = "ubuntu-base-22.04.5-base-amd64.tar.gz"
BASE_URL = (
    "https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/" + BASE_NAME
)
MIRROR = "http://archive.ubuntu.com/ubuntu"
SUITE = "jammy"
ARCH = "amd64"
UA = "GTOS-glibc-fetch/1.6"

# Минимальный набор для Electron/Cursor под X11
SEED = [
    "ca-certificates",
    "libnss3",
    "libnspr4",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libcups2",
    "libdrm2",
    "libdbus-1-3",
    "libxcb1",
    "libxkbcommon0",
    "libx11-6",
    "libxcomposite1",
    "libxdamage1",
    "libxext6",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libpango-1.0-0",
    "libcairo2",
    "libasound2",
    "libgtk-3-0",
    "libxshmfence1",
    "libglib2.0-0",
    "libgdk-pixbuf-2.0-0",
    "libpangocairo-1.0-0",
    "fonts-dejavu-core",
    "fontconfig",
    "libstdc++6",
    "libgcc-s1",
    "zlib1g",
    # зависимости VS Code / Cursor (.deb Depends)
    "libxkbfile1",
    "libsecret-1-0",
    "libcurl3-gnutls",
    "libatspi2.0-0",
    "libexpat1",
    "libxss1",
    "libxtst6",
    "libnotify4",
    "libuuid1",
    "xdg-utils",
]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        print(f"skip {dest.name} ({dest.stat().st_size} bytes)")
        return
    print(f"get {url}")
    dest.write_bytes(_get(url))
    print(f"  -> {dest} ({dest.stat().st_size} bytes)")


def parse_packages(blob: bytes) -> dict[str, dict[str, str]]:
    text = gzip.decompress(blob).decode("utf-8", "replace")
    pkgs: dict[str, dict[str, str]] = {}
    cur: dict[str, str] = {}
    key = ""
    for line in text.splitlines():
        if not line:
            name = cur.get("Package")
            if name and cur.get("Filename"):
                pkgs[name] = cur
            cur = {}
            key = ""
            continue
        if line.startswith(" ") and key:
            cur[key] = cur.get(key, "") + " " + line.strip()
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            cur[key] = v.strip()
    return pkgs


def dep_names(field: str) -> list[str]:
    out: list[str] = []
    for part in field.split(","):
        part = part.strip()
        if not part or part.startswith("|"):
            continue
        # first alternative only
        alt = part.split("|")[0].strip()
        name = alt.split("(")[0].strip().split(":")[0].strip()
        if name and name not in ("Pre-Depends",):
            out.append(name)
    return out


def resolve(pkgs: dict[str, dict[str, str]], seeds: list[str]) -> list[str]:
    need: list[str] = []
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        meta = pkgs.get(name)
        if not meta:
            continue
        need.append(name)
        for field in ("Depends", "Pre-Depends"):
            for dep in dep_names(meta.get(field, "")):
                if dep not in seen:
                    stack.append(dep)
    return need


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    base = CACHE / BASE_NAME
    _download(BASE_URL, base)

    idx = CACHE / f"Packages-{SUITE}-{ARCH}.gz"
    _download(f"{MIRROR}/dists/{SUITE}/main/binary-{ARCH}/Packages.gz", idx)
    # universe for some libs
    idx_u = CACHE / f"Packages-{SUITE}-universe-{ARCH}.gz"
    _download(f"{MIRROR}/dists/{SUITE}/universe/binary-{ARCH}/Packages.gz", idx_u)

    pkgs = parse_packages(idx.read_bytes())
    pkgs.update(parse_packages(idx_u.read_bytes()))
    names = resolve(pkgs, SEED)
    print(f"resolved {len(names)} packages")

    deb_dir = CACHE / "glibc-debs"
    deb_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for name in names:
        meta = pkgs[name]
        rel = meta["Filename"]
        dest = deb_dir / Path(rel).name
        _download(f"{MIRROR}/{rel}", dest)
        downloaded.append(dest)

    bundle = CACHE / "glibc-debs.tar.gz"
    print(f"pack {bundle}")
    with tarfile.open(bundle, "w:gz") as tar:
        for p in downloaded:
            tar.add(p, arcname=f"debs/{p.name}")
        # install helper
        helper = (
            "#!/bin/sh\n"
            "set -eu\n"
            "cd /tmp/gtos-glibc-debs/debs\n"
            "DEBIAN_FRONTEND=noninteractive dpkg -i *.deb || true\n"
            "DEBIAN_FRONTEND=noninteractive apt-get install -f -y --no-install-recommends || true\n"
        ).encode()
        info = tarfile.TarInfo(name="install-debs.sh")
        info.size = len(helper)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(helper))
    print(f"done base={base.stat().st_size} debs={bundle.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
