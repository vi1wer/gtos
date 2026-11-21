#!/usr/bin/env python3
"""Собрать готовый glibc-root офлайн (без dpkg в госте).

Работает потоково tar→tar: ничего не распаковывается на NTFS, поэтому
сохраняются симлинки (libX11.so.6 → …, ld-linux) и права на исполнение.
"""

from __future__ import annotations

import gzip
import io
import lzma
import posixpath
import tarfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache"
BASE = CACHE / "ubuntu-base-22.04.5-base-amd64.tar.gz"
DEBS = CACHE / "glibc-debs"
OUT_TAR = CACHE / "gtos-glibc-root.tar.gz"
ROOT_VERSION = "4"


def _ar_members(data: bytes) -> dict[str, bytes]:
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    pos = 8
    out: dict[str, bytes] = {}
    while pos + 60 <= len(data):
        header = data[pos : pos + 60]
        pos += 60
        name = header[0:16].decode("ascii", "replace").strip()
        size = int(header[48:58].decode("ascii", "replace").strip() or "0")
        payload = data[pos : pos + size]
        pos += size + (size & 1)
        if name.endswith("/"):
            name = name[:-1]
        out[name] = payload
    return out


def _decompress_tar(blob: bytes) -> bytes:
    if blob[:2] == b"\x1f\x8b":
        return gzip.decompress(blob)
    if blob[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(blob)
    if blob[:4] == b"\x28\xb5\x2f\xfd":
        import zstandard as zstd  # type: ignore

        dctx = zstd.ZstdDecompressor()
        try:
            return dctx.decompress(blob)
        except zstd.ZstdError:
            return dctx.decompress(blob, max_output_size=512 * 1024 * 1024)
    if b"ustar" in blob[:300]:
        return blob
    try:
        return zlib.decompress(blob)
    except zlib.error:
        return blob


MERGED = {"bin": "usr/bin", "sbin": "usr/sbin", "lib": "usr/lib", "lib64": "usr/lib64"}


def remap_name(name: str) -> str | None:
    """merged-usr: bin/lib/sbin/lib64 → usr/… (сами ярлыки добавим в конце)."""
    while name.startswith("./"):
        name = name[2:]
    name = name.strip("/")
    if not name or name == "." or name.startswith(".."):
        return None
    for src, dst in MERGED.items():
        if name == src:
            return None
        if name.startswith(src + "/"):
            return dst + "/" + name[len(src) + 1 :]
    return name


def _relative_link(name: str, linkname: str) -> str:
    """Абсолютные ссылки на хосте (musl) указывают мимо root — делаем относительными."""
    if not linkname.startswith("/"):
        return linkname
    target = remap_name(linkname) or linkname.lstrip("/")
    return posixpath.relpath(target, posixpath.dirname(name) or ".")


class RootImage:
    def __init__(self) -> None:
        self.entries: dict[str, tuple[tarfile.TarInfo, bytes | None]] = {}

    def apply(self, tar: tarfile.TarFile) -> None:
        for m in tar.getmembers():
            name = remap_name(m.name)
            if name is None:
                continue
            info = tarfile.TarInfo(name)
            info.mode = m.mode
            info.mtime = m.mtime
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if m.isdir():
                info.type = tarfile.DIRTYPE
                prev = self.entries.get(name)
                if prev and prev[0].type == tarfile.SYMTYPE:
                    continue
                self.entries[name] = (info, None)
            elif m.issym():
                info.type = tarfile.SYMTYPE
                info.linkname = _relative_link(name, m.linkname)
                prev = self.entries.get(name)
                if prev and prev[0].isdir():
                    continue
                self.entries[name] = (info, None)
            elif m.islnk():
                target = remap_name(m.linkname)
                src = self.entries.get(target or "")
                if src is None or src[1] is None:
                    continue
                info.type = tarfile.REGTYPE
                info.size = len(src[1])
                self.entries[name] = (info, src[1])
            elif m.isfile():
                f = tar.extractfile(m)
                data = f.read() if f else b""
                info.type = tarfile.REGTYPE
                info.size = len(data)
                self.entries[name] = (info, data)

    def put_file(self, name: str, data: bytes, mode: int = 0o644) -> None:
        info = tarfile.TarInfo(name)
        info.type = tarfile.REGTYPE
        info.mode = mode
        info.mtime = int(time.time())
        info.size = len(data)
        self.entries[name] = (info, data)

    def get(self, name: str) -> bytes | None:
        e = self.entries.get(name)
        return e[1] if e else None

    def ensure_dir(self, name: str) -> None:
        if name not in self.entries:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o1777 if name == "tmp" else 0o755
            info.mtime = int(time.time())
            self.entries[name] = (info, None)


def deb_data_tar(deb: Path) -> tarfile.TarFile | None:
    members = _ar_members(deb.read_bytes())
    for key, val in members.items():
        if key.startswith("data.tar"):
            return tarfile.open(fileobj=io.BytesIO(_decompress_tar(val)), mode="r:")
    return None


def main() -> int:
    if not BASE.is_file():
        raise SystemExit(f"нет {BASE}")
    if not DEBS.is_dir():
        raise SystemExit(f"нет {DEBS}")

    img = RootImage()
    print("apply base")
    with tarfile.open(BASE, "r:gz") as tar:
        img.apply(tar)

    debs = sorted(DEBS.glob("*.deb"))
    print(f"apply {len(debs)} debs")
    for i, deb in enumerate(debs, 1):
        tar = deb_data_tar(deb)
        if tar is None:
            print(f"  skip {deb.name}: no data.tar")
            continue
        with tar:
            img.apply(tar)
        if i % 25 == 0 or i == len(debs):
            print(f"  {i}/{len(debs)} {deb.name}")

    for d in ("home", "tmp", "dev", "proc", "sys", "opt", "run", "usr/bin", "usr/sbin", "usr/lib", "usr/lib64"):
        img.ensure_dir(d)

    passwd = img.get("etc/passwd") or b""
    if b"misha:" not in passwd:
        img.put_file("etc/passwd", passwd + b"misha:x:1000:1000:Misha:/home/misha:/bin/bash\n")
    group = img.get("etc/group") or b""
    if b"misha:" not in group:
        img.put_file("etc/group", group + b"misha:x:1000:\n")
    img.put_file("etc/resolv.conf", b"nameserver 1.1.1.1\nnameserver 8.8.8.8\n")
    img.put_file(".gtos-ok", b"1\n")
    img.put_file(".gtos-electron-ok", b"1\n")
    img.put_file(".gtos-root-version", (ROOT_VERSION + "\n").encode())

    libdir = "usr/lib/x86_64-linux-gnu/"
    need = ["libX11.so.6", "libnss3.so", "libgtk-3.so.0", "libgbm.so.1", "libasound.so.2", "libc.so.6", "ld-linux-x86-64.so.2"]
    missing = [n for n in need if libdir + n not in img.entries]
    if "usr/lib64/ld-linux-x86-64.so.2" not in img.entries:
        missing.append("usr/lib64/ld-linux-x86-64.so.2")
    if "usr/bin/sh" not in img.entries:
        missing.append("usr/bin/sh")
    syms = sum(1 for i, _ in img.entries.values() if i.type == tarfile.SYMTYPE)
    print(f"entries={len(img.entries)} symlinks={syms} missing={missing}")
    if missing:
        raise SystemExit("в корне не хватает: " + ", ".join(missing))

    if OUT_TAR.exists():
        OUT_TAR.unlink()
    print(f"pack {OUT_TAR}")
    with tarfile.open(OUT_TAR, "w:gz", compresslevel=6, format=tarfile.GNU_FORMAT) as out:
        for link, target in MERGED.items():
            info = tarfile.TarInfo(link)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            info.mode = 0o777
            out.addfile(info)
        for name in sorted(img.entries):
            info, data = img.entries[name]
            out.addfile(info, io.BytesIO(data) if data is not None else None)
    mb = OUT_TAR.stat().st_size / (1024 * 1024)
    print(f"done {OUT_TAR.name} ({mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
