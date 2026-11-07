#!/usr/bin/env python3
"""Собрать загружаемый ISO GT/OS (BIOS + UEFI El Torito)."""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import tarfile
import urllib.request
import zlib
from pathlib import Path

import pycdlib

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
CACHE = ROOT / "cache" / "syslinux"
EFI_CACHE = ROOT / "cache" / "efi"
USER_AGENT = "GTOS-iso/1.6"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as resp:
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
    isolinux = CACHE / "isolinux.bin"
    ldlinux = CACHE / "ldlinux.c32"
    isohdpfx = CACHE / "isohdpfx.bin"
    if isolinux.is_file() and ldlinux.is_file() and isolinux.stat().st_size > 1000:
        return isolinux.read_bytes(), ldlinux.read_bytes(), isohdpfx.read_bytes() if isohdpfx.is_file() else b""

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
    return isolinux.read_bytes(), ldlinux.read_bytes(), isohdpfx.read_bytes() if isohdpfx.is_file() else b""


def fetch_efi_bits() -> tuple[bytes, bytes]:
    """Alpine virt ISO → efi.img + BOOTX64.EFI (кэш)."""
    EFI_CACHE.mkdir(parents=True, exist_ok=True)
    efi_img = EFI_CACHE / "efi.img"
    bootx64 = EFI_CACHE / "BOOTX64.EFI"
    if efi_img.is_file() and bootx64.is_file() and efi_img.stat().st_size > 100_000:
        return efi_img.read_bytes(), bootx64.read_bytes()

    yaml = urllib.request.urlopen(
        urllib.request.Request(
            "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/latest-releases.yaml",
            headers={"User-Agent": USER_AGENT},
        ),
        timeout=60,
    ).read().decode()
    m = re.search(r"file:\s*(alpine-virt-[\d.]+-x86_64\.iso)", yaml)
    if not m:
        raise SystemExit("не найден alpine-virt ISO")
    name = m.group(1)
    iso_path = EFI_CACHE / name
    if not iso_path.is_file() or iso_path.stat().st_size < 1_000_000:
        url = f"https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/{name}"
        print(f"download {name} for UEFI boot…")
        _download(url, iso_path)

    iso = pycdlib.PyCdlib()
    iso.open(str(iso_path))
    for rr, dest in (
        ("/boot/grub/efi.img", efi_img),
        ("/efi/boot/bootx64.efi", bootx64),
    ):
        buf = io.BytesIO()
        iso.get_file_from_iso_fp(buf, rr_path=rr)
        dest.write_bytes(buf.getvalue())
        print(f"cached {dest.name} ({len(buf.getvalue())} bytes)")
    iso.close()
    return efi_img.read_bytes(), bootx64.read_bytes()


def grub_cfg(version: str) -> bytes:
    append = "rdinit=/init console=tty0 quiet loglevel=3 video=1920x1080"
    safe = append + " gtos.safemode=1"
    text = f"""set timeout=5
set default=0

menuentry "GT/OS {version}" {{
    linux /boot/vmlinuz {append}
    initrd /boot/initrd.gz
}}
menuentry "GT/OS {version} (Safe Mode)" {{
    linux /boot/vmlinuz {safe}
    initrd /boot/initrd.gz
}}
menuentry "GT/OS {version} (verbose)" {{
    linux /boot/vmlinuz rdinit=/init console=tty0 loglevel=7 video=1920x1080
    initrd /boot/initrd.gz
}}
"""
    return text.encode("utf-8")


def write_sha256(iso_path: Path) -> Path:
    h = hashlib.sha256()
    with iso_path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    digest = h.hexdigest()
    out = iso_path.with_suffix(iso_path.suffix + ".sha256")
    out.write_text(f"{digest}  {iso_path.name}\n", encoding="utf-8")
    print(f"sha256 {digest}")
    return out


def build_iso(version: str) -> Path:
    kernel = OUT / "vmlinuz"
    initrd = OUT / "gtos-rootfs.cpio.gz"
    if not kernel.is_file() or not initrd.is_file():
        raise SystemExit("нет out/vmlinuz или out/gtos-rootfs.cpio.gz — сначала python build.py")

    isolinux_bin, ldlinux_c32, _isohdpfx = fetch_syslinux_bits()
    efi_img, bootx64 = fetch_efi_bits()
    grub_bytes = grub_cfg(version)

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
  APPEND {append} gtos.safemode=1
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

Загрузка: BIOS (isolinux) и UEFI (El Torito EFI).

Меню:
  gtos / «GT/OS»           — обычный режим
  safemode / Safe Mode     — минимум служб
  verbose                  — подробный лог

Файлы:
  /boot/vmlinuz
  /boot/initrd.gz
  /boot/grub/grub.cfg
  /boot/grub/efi.img
  /EFI/BOOT/BOOTX64.EFI
  /boot/isolinux/*

Проверка:
  sha256sum -c GTOS-{version}-x86_64.iso.sha256

QEMU:
  python run.py
  python run.py --safe

Установка: Пуск → Установка GT/OS
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
    iso.add_directory("/BOOT/GRUB", rr_name="grub", joliet_path="/boot/grub")
    iso.add_directory("/EFI", rr_name="efi", joliet_path="/efi")
    iso.add_directory("/EFI/BOOT", rr_name="boot", joliet_path="/efi/boot")

    iso.add_fp(kernel.open("rb"), kernel.stat().st_size, "/BOOT/VMLINUZ.;1", rr_name="vmlinuz", joliet_path="/boot/vmlinuz")
    iso.add_fp(initrd.open("rb"), initrd.stat().st_size, "/BOOT/INITRD.GZ;1", rr_name="initrd.gz", joliet_path="/boot/initrd.gz")
    iso.add_fp(io.BytesIO(isolinux_bin), len(isolinux_bin), "/BOOT/ISOLINUX/ISOLINUX.BIN;1", rr_name="isolinux.bin", joliet_path="/boot/isolinux/isolinux.bin")
    iso.add_fp(io.BytesIO(ldlinux_c32), len(ldlinux_c32), "/BOOT/ISOLINUX/LDLINUX.C32;1", rr_name="ldlinux.c32", joliet_path="/boot/isolinux/ldlinux.c32")
    iso.add_fp(io.BytesIO(isolinux_cfg), len(isolinux_cfg), "/BOOT/ISOLINUX/ISOLINUX.CFG;1", rr_name="isolinux.cfg", joliet_path="/boot/isolinux/isolinux.cfg")
    iso.add_fp(io.BytesIO(grub_bytes), len(grub_bytes), "/BOOT/GRUB/GRUB.CFG;1", rr_name="grub.cfg", joliet_path="/boot/grub/grub.cfg")
    iso.add_fp(io.BytesIO(efi_img), len(efi_img), "/BOOT/GRUB/EFI.IMG;1", rr_name="efi.img", joliet_path="/boot/grub/efi.img")
    iso.add_fp(io.BytesIO(bootx64), len(bootx64), "/EFI/BOOT/BOOTX64.EFI;1", rr_name="bootx64.efi", joliet_path="/efi/boot/bootx64.efi")
    iso.add_fp(io.BytesIO(readme), len(readme), "/README.TXT;1", rr_name="README.txt", joliet_path="/README.txt")

    # BIOS El Torito
    iso.add_eltorito(
        "/BOOT/ISOLINUX/ISOLINUX.BIN;1",
        boot_load_size=4,
        media_name="noemul",
        boot_info_table=True,
    )
    # UEFI El Torito (platform 0xEF)
    efi_sectors = (len(efi_img) + 511) // 512
    iso.add_eltorito(
        "/BOOT/GRUB/EFI.IMG;1",
        boot_load_size=efi_sectors,
        media_name="noemul",
        efi=True,
        platform_id=0xEF,
        bootable=True,
    )

    iso_path.parent.mkdir(parents=True, exist_ok=True)
    if iso_path.exists():
        iso_path.unlink()
    iso.write(str(iso_path))
    iso.close()
    sha = write_sha256(iso_path)
    mb = iso_path.stat().st_size / (1024 * 1024)
    print(f"wrote {iso_path} ({mb:.1f} MB) — BIOS + UEFI · {sha.name}")
    return iso_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка загружаемого ISO GT/OS")
    parser.add_argument("--version", default="1.6", help="Версия выпуска")
    args = parser.parse_args()
    build_iso(args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
