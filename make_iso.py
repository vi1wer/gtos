#!/usr/bin/env python3
"""Собрать загружаемый ISO GT/OS (BIOS El Torito + файлы для UEFI/Ventoy)."""

from __future__ import annotations

import argparse
import io
import tarfile
import tempfile
import urllib.request
import zlib
from pathlib import Path

import pycdlib

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
CACHE = ROOT / "cache" / "syslinux"
USER_AGENT = "GTOS-iso/1.5"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _apk_payloads(blob: bytes) -> list[bytes]:
    pos = blob.find(b"\x1f\x8b")
    out: list[bytes] = []
    while pos != -1 and pos < len(blob):
        dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            payload = dec.decompress(blob[pos:]) + dec.flush()
        except zlib.error:
            pos = blob.find(b"\x1f\x8b", pos + 2)
            continue
        out.append(payload)
        unused = dec.unused_data
        if not unused:
            break
        end = len(blob) - len(unused)
        rel = unused.find(b"\x1f\x8b")
        if rel < 0:
            break
        pos = end + rel
    return out


def fetch_syslinux_bits() -> tuple[bytes, bytes, bytes]:
    """isolinux.bin, ldlinux.c32, isohdpfx.bin из пакета Alpine syslinux."""
    marker = CACHE / "ready.txt"
    isolinux = CACHE / "isolinux.bin"
    ldlinux = CACHE / "ldlinux.c32"
    isohdpfx = CACHE / "isohdpfx.bin"
    if isolinux.is_file() and ldlinux.is_file() and isolinux.stat().st_size > 1000:
        return isolinux.read_bytes(), ldlinux.read_bytes(), isohdpfx.read_bytes() if isohdpfx.is_file() else b""

    # актуальный APKINDEX → пакет syslinux
    idx_url = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/x86_64/APKINDEX.tar.gz"
    idx_path = CACHE / "APKINDEX.tar.gz"
    print("download Alpine APKINDEX for syslinux…")
    _download(idx_url, idx_path)
    pkg_file = None
    with tarfile.open(idx_path, "r:gz") as tar:
        text = tar.extractfile(tar.getmember("APKINDEX")).read().decode("utf-8", "replace")
    block: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            if block.get("P") == "syslinux":
                pkg_file = f"{block['P']}-{block['V']}.apk"
                break
            block = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            block[k] = v
    if not pkg_file:
        raise SystemExit("не найден пакет syslinux в Alpine")

    apk_url = f"https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/x86_64/{pkg_file}"
    apk_path = CACHE / pkg_file
    print(f"download {pkg_file}…")
    _download(apk_url, apk_path)
    wanted = {
        "usr/share/syslinux/isolinux.bin": isolinux,
        "usr/share/syslinux/ldlinux.c32": ldlinux,
        "usr/share/syslinux/isohdpfx.bin": isohdpfx,
    }
    for payload in _apk_payloads(apk_path.read_bytes()):
        bio = io.BytesIO(payload)
        try:
            with tarfile.open(fileobj=bio, mode="r:") as tar:
                for mem in tar.getmembers():
                    name = mem.name.lstrip("./")
                    if name in wanted and mem.isfile():
                        data = tar.extractfile(mem).read()
                        wanted[name].parent.mkdir(parents=True, exist_ok=True)
                        wanted[name].write_bytes(data)
        except tarfile.TarError:
            continue
    if not isolinux.is_file() or not ldlinux.is_file():
        raise SystemExit("не удалось извлечь isolinux.bin / ldlinux.c32")
    marker.write_text("ok\n", encoding="utf-8")
    return isolinux.read_bytes(), ldlinux.read_bytes(), isohdpfx.read_bytes() if isohdpfx.is_file() else b""


def build_iso(version: str) -> Path:
    kernel = OUT / "vmlinuz"
    initrd = OUT / "gtos-rootfs.cpio.gz"
    if not kernel.is_file() or not initrd.is_file():
        raise SystemExit("нет out/vmlinuz или out/gtos-rootfs.cpio.gz — сначала python build.py")

    isolinux_bin, ldlinux_c32, _isohdpfx = fetch_syslinux_bits()

    iso_path = OUT / f"GTOS-{version}-x86_64.iso"
    ver_flat = version.replace(".", "")
    append = "rdinit=/init console=tty0 quiet loglevel=3 video=1920x1080"
    isolinux_cfg = f"""DEFAULT gtos
PROMPT 1
TIMEOUT 50
LABEL gtos
  MENU LABEL GT/OS {version}
  KERNEL /boot/vmlinuz
  APPEND {append}
  INITRD /boot/initrd.gz
LABEL safemode
  MENU LABEL GT/OS {version} (Safe Mode)
  KERNEL /boot/vmlinuz
  APPEND rdinit=/init console=tty0 quiet loglevel=3 video=1920x1080 gtos.safemode=1
  INITRD /boot/initrd.gz
LABEL verbose
  MENU LABEL GT/OS {version} (verbose)
  KERNEL /boot/vmlinuz
  APPEND rdinit=/init console=tty0 loglevel=7 video=1920x1080
  INITRD /boot/initrd.gz
""".encode("utf-8")

    readme = f"""GT/OS {version}
==========

Продукт Glukhov Mikhail.

Загружаемый образ (BIOS / Legacy). Для UEFI используйте Ventoy
или загрузите ядро вручную из /boot.

Меню загрузки (Tab):
  gtos      — обычный режим
  safemode — безопасный режим (минимум служб)
  verbose  — подробный лог

Файлы:
  /boot/vmlinuz
  /boot/initrd.gz
  /boot/isolinux/*

QEMU:
  python run.py
  python run.py --safe

Установка на диск: Пуск → Установка GT/OS

Поддержка: mikhail.lososka@gmail.com
""".encode("utf-8")

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        joliet=3,
        rock_ridge="1.09",
        vol_ident=f"GTOS_{ver_flat}"[:32],
    )
    iso.add_directory("/BOOT", rr_name="boot", joliet_path="/boot")
    iso.add_directory("/BOOT/ISOLINUX", rr_name="isolinux", joliet_path="/boot/isolinux")

    iso.add_fp(kernel.open("rb"), kernel.stat().st_size, "/BOOT/VMLINUZ.;1", rr_name="vmlinuz", joliet_path="/boot/vmlinuz")
    iso.add_fp(initrd.open("rb"), initrd.stat().st_size, "/BOOT/INITRD.GZ;1", rr_name="initrd.gz", joliet_path="/boot/initrd.gz")
    iso.add_fp(io.BytesIO(isolinux_bin), len(isolinux_bin), "/BOOT/ISOLINUX/ISOLINUX.BIN;1", rr_name="isolinux.bin", joliet_path="/boot/isolinux/isolinux.bin")
    iso.add_fp(io.BytesIO(ldlinux_c32), len(ldlinux_c32), "/BOOT/ISOLINUX/LDLINUX.C32;1", rr_name="ldlinux.c32", joliet_path="/boot/isolinux/ldlinux.c32")
    iso.add_fp(io.BytesIO(isolinux_cfg), len(isolinux_cfg), "/BOOT/ISOLINUX/ISOLINUX.CFG;1", rr_name="isolinux.cfg", joliet_path="/boot/isolinux/isolinux.cfg")
    iso.add_fp(io.BytesIO(readme), len(readme), "/README.TXT;1", rr_name="README.txt", joliet_path="/README.txt")

    # El Torito BIOS boot
    iso.add_eltorito(
        "/BOOT/ISOLINUX/ISOLINUX.BIN;1",
        boot_load_size=4,
        media_name="noemul",
        boot_info_table=True,
    )

    iso_path.parent.mkdir(parents=True, exist_ok=True)
    if iso_path.exists():
        iso_path.unlink()
    iso.write(str(iso_path))
    iso.close()
    mb = iso_path.stat().st_size / (1024 * 1024)
    print(f"wrote {iso_path} ({mb:.1f} MB) — BIOS bootable")
    return iso_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка загружаемого ISO GT/OS")
    parser.add_argument("--version", default="1.5", help="Версия выпуска")
    args = parser.parse_args()
    # fix typo guard
    build_iso(args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
