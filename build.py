#!/usr/bin/env python3
"""Build GT/OS: Linux kernel + Qt 6 QML shell packed as an initramfs."""

from __future__ import annotations

import base64
import gzip
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
APK_CACHE = CACHE / "apk"
OUT = ROOT / "out"

REPOS = ("main", "community")
USER_AGENT = "GTOS-builder/1.1"
GTOS_VERSION = "1.5"

RUNTIME_PACKAGES = [
    "busybox",
    "alpine-baselayout",
    "alpine-baselayout-data",
    "musl",
    # ядро для реального ПК (не virt)
    "linux-lts",
    "kmod",
    "eudev",
    # firmware Wi‑Fi / GPU / NIC (без огромного nvidia)
    "linux-firmware-intel",
    "linux-firmware-amd",
    "linux-firmware-other",
    "linux-firmware-ath10k",
    "linux-firmware-ath11k",
    "linux-firmware-mediatek",
    "linux-firmware-realtek",
    "font-dejavu",
    "fontconfig",
    "xorg-server",
    "xf86-video-modesetting",
    "xf86-input-evdev",
    "xf86-input-libinput",
    "xinit",
    "xset",
    "setxkbmap",
    "xkeyboard-config",
    "mesa",
    "mesa-gl",
    "mesa-dri-gallium",
    "qt6-qtbase",
    "qt6-qtbase-x11",
    "qt6-qtdeclarative",
    # сеть / Wi‑Fi
    "iproute2",
    "iputils",
    "dhcpcd",
    "wpa_supplicant",
    "wireless-tools",
    "curl",
    "ca-certificates",
    "openssl",
    # диск / загрузчик
    "e2fsprogs",
    "dosfstools",
    "sfdisk",
    "grub",
    "grub-bios",
    "grub-efi",
    "efibootmgr",
    "lsblk",
    "blkid",
    "pciutils",
    "wireless-tools",
    "su-exec",
    "util-linux-misc",
    "nano",
    "openssh-client",
    # звук
    "alsa-utils",
    "alsa-lib",
    "alsa-ucm-conf",
    # браузер для повседневной работы
    "firefox",
    # рамки/крестики у окон внешних приложений (Firefox и др.)
    "openbox",
    # медиа
    "ffmpeg",
    "mpg123",
    "vlc",
    "apk-tools",
    "alpine-keys",
    # PDF / буфер / уведомления / печать
    "poppler-utils",
    "xclip",
    "dbus",
    "dbus-x11",
    "dunst",
    "cups",
    "cups-filters",
]

BUILD_EXTRA = [
    "g++",
    "musl-dev",
    "pkgconf",
    "make",
    "qt6-qtbase-dev",
    "qt6-qtdeclarative-dev",
]

# Лёгкий набор только для компиляции gt-shell в QEMU (virt-ядро быстрее)
COMPILE_PACKAGES = [
    "busybox",
    "alpine-baselayout",
    "alpine-baselayout-data",
    "musl",
    "linux-virt",
    "kmod",
    "eudev",
    "font-dejavu",
    "fontconfig",
    "xorg-server",
    "xf86-video-modesetting",
    "xf86-input-libinput",
    "xinit",
    "mesa",
    "mesa-gl",
    "qt6-qtbase",
    "qt6-qtbase-x11",
    "qt6-qtdeclarative",
    "curl",
    "ca-certificates",
    "openssl",
]

SKIP_PACKAGES = {
    # слишком тяжёлые / не нужны в initrd
    "linux-firmware-nvidia",
    "linux-firmware",
    "linux-firmware-any",
    "linux-firmware-none",
    "linux-firmware-dell",
    "linux-firmware-hp",
    "linux-firmware-lenovo",
    "linux-firmware-cirrus",
    "linux-firmware-liquidio",
    "linux-firmware-mellanox",
    "linux-firmware-qlogic",
    "linux-firmware-radeon",
    "qt6-qtbase-mysql",
    "qt6-qtbase-odbc",
    "qt6-qtbase-postgresql",
    "qt6-qtbase-sqlite",
    "qt6-qtbase-wayland",
}
DEV_OK = {
    "musl-dev",
    "libstdc++-dev",
    "qt6-qtbase-dev",
    "qt6-qtdeclarative-dev",
    "qt6-qtshadertools-dev",
    "qt6-qtsvg-dev",
}
SKIP_DEPS = {"initramfs-generator"}


def log(msg: str) -> None:
    print(msg, flush=True)


def ver_key(version: str) -> list:
    parts: list = []
    token = ""
    for ch in version:
        if ch.isdigit():
            token += ch
            continue
        if token:
            parts.append(int(token))
            token = ""
        parts.append(ch)
    if token:
        parts.append(int(token))
    return parts


def download(url: str, dest: Path, expected: int | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        if not expected or dest.stat().st_size == expected:
            return dest
        dest.unlink()
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            log(f"  download {url}")
            with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as out:
                shutil.copyfileobj(resp, out)
                length = resp.headers.get("Content-Length")
            size = tmp.stat().st_size
            if length and size != int(length):
                raise OSError(f"short download {size} != {length}")
            if expected and size != expected:
                raise OSError(f"short download {size} != {expected}")
            tmp.replace(dest)
            return dest
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log(f"  retry {attempt + 1}: {exc}")
            time.sleep(2 + attempt * 2)
            if tmp.exists():
                tmp.unlink()
    raise RuntimeError(f"failed to download {url}: {last_err}")


def parse_apkindex(text: str, repo: str, repo_base: str) -> list[dict]:
    packages: list[dict] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            if current.get("P"):
                current["repo"] = repo
                current["repo_base"] = repo_base
                packages.append(current)
            current = {}
            continue
        if len(line) >= 2 and line[1] == ":":
            key, value = line[0], line[2:]
            if key in current and key in {"D", "p"}:
                current[key] += " " + value
            else:
                current[key] = value
    if current.get("P"):
        current["repo"] = repo
        current["repo_base"] = repo_base
        packages.append(current)
    return packages


def detect_branch() -> str:
    url = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/latest-releases.yaml"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("branch:"):
            branch = line.split(":", 1)[1].strip()
            if branch.startswith("v"):
                return branch
    raise RuntimeError("cannot detect alpine branch")


def load_indexes(branch_root: str) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_name: dict[str, dict] = {}
    all_pkgs: list[dict] = []
    for repo in REPOS:
        repo_base = f"{branch_root}/{repo}/x86_64"
        dest = CACHE / f"APKINDEX-{repo}.tar.gz"
        download(f"{repo_base}/APKINDEX.tar.gz", dest)
        with tarfile.open(dest, "r:gz") as tar:
            text = tar.extractfile(tar.getmember("APKINDEX")).read().decode("utf-8", "replace")
        all_pkgs.extend(parse_apkindex(text, repo, repo_base))
    for pkg in all_pkgs:
        name = pkg["P"]
        prev = by_name.get(name)
        if prev is None or ver_key(pkg["V"]) > ver_key(prev["V"]):
            by_name[name] = pkg
    providers: dict[str, list[dict]] = {}
    for pkg in by_name.values():
        names = {pkg["P"]}
        for item in pkg.get("p", "").split():
            names.add(item.split("=")[0])
        for name in names:
            providers.setdefault(name, []).append(pkg)
    return by_name, providers


def dep_names(pkg: dict) -> list[str]:
    result = []
    for item in pkg.get("D", "").split():
        if item.startswith("!"):
            continue
        name = item
        for sep in ("=", ">", "<", "~"):
            name = name.split(sep)[0]
        if name:
            result.append(name)
    return result


def resolve(by_name: dict[str, dict], providers: dict[str, list[dict]], roots: list[str]) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    missing: list[str] = []

    def find(name: str) -> dict | None:
        if name in by_name:
            return by_name[name]
        cands = providers.get(name) or []
        if not cands:
            return None
        return min(cands, key=lambda pkg: int(pkg.get("I") or 10**12))

    def visit(name: str) -> None:
        pkg = find(name)
        if pkg is None:
            missing.append(name)
            return
        real = pkg["P"]
        if real in SKIP_PACKAGES or real.endswith(("-doc", "-dbg")):
            return
        if real.startswith("dracut"):
            return
        if real.endswith("-dev") and real not in DEV_OK:
            return
        if "webengine" in real or "webview" in real or "qtweb" in real:
            return
        if real in seen:
            return
        seen.add(real)
        for dep in dep_names(pkg):
            if dep in SKIP_DEPS:
                continue
            visit(dep)
        selected.append(pkg)

    for root in roots:
        visit(root)
    if missing:
        log("warning: unresolved: " + ", ".join(sorted(set(missing))[:40]))
    return selected


def gzip_payloads(blob: bytes) -> list[bytes]:
    pos = blob.find(b"\x1f\x8b")
    payloads: list[bytes] = []
    while pos != -1 and pos < len(blob):
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            payload = decompressor.decompress(blob[pos:]) + decompressor.flush()
        except zlib.error:
            pos = blob.find(b"\x1f\x8b", pos + 2)
            continue
        payloads.append(payload)
        unused = decompressor.unused_data
        if not unused:
            break
        end = len(blob) - len(unused)
        rel = unused.find(b"\x1f\x8b")
        if rel < 0:
            break
        pos = end + rel
    return payloads


def norm_path(name: str) -> str:
    name = name.replace("\\", "/").lstrip("/")
    while name.startswith("./"):
        name = name[2:]
    return name


class FsNode:
    __slots__ = ("kind", "mode", "data", "rmajor", "rminor")

    def __init__(self, kind: str, mode: int, data: bytes = b"", rmajor: int = 0, rminor: int = 0):
        self.kind = kind
        self.mode = mode
        self.data = data
        self.rmajor = rmajor
        self.rminor = rminor


def add_node(tree: dict[str, FsNode], path: str, node: FsNode) -> None:
    path = norm_path(path)
    if path in ("", "."):
        return
    tree[path] = node
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    while parent:
        if parent not in tree:
            tree[parent] = FsNode("dir", 0o040755)
        if "/" not in parent:
            break
        parent = parent.rsplit("/", 1)[0]


def ingest_tar(tree: dict[str, FsNode], payload: bytes, kernel_out: list[bytes]) -> None:
    try:
        tar = tarfile.open(fileobj=io.BytesIO(payload), mode="r:")
    except tarfile.TarError:
        return
    contents: dict[str, bytes] = {}
    members = [m for m in tar.getmembers() if m.name]
    for member in members:
        path = norm_path(member.name)
        if not path or path.startswith(".SIGN") or path in {".PKGINFO"}:
            continue
        if member.isreg():
            extracted = tar.extractfile(member)
            contents[path] = extracted.read() if extracted else b""
    for member in members:
        path = norm_path(member.name)
        if not path or path.startswith(".SIGN") or path in {".PKGINFO"}:
            continue
        mode = member.mode & 0o7777
        if member.issym():
            add_node(tree, path, FsNode("lnk", 0o120000 | (mode or 0o777), member.linkname.encode()))
        elif member.isdir():
            add_node(tree, path, FsNode("dir", 0o040000 | (mode or 0o755)))
        elif member.ischr():
            add_node(tree, path, FsNode("chr", 0o020000 | mode, rmajor=member.devmajor or 0, rminor=member.devminor or 0))
        elif member.isblk():
            add_node(tree, path, FsNode("blk", 0o060000 | mode, rmajor=member.devmajor or 0, rminor=member.devminor or 0))
        elif member.isfifo():
            add_node(tree, path, FsNode("fifo", 0o010000 | mode))
        elif member.islnk() or member.isreg():
            data = contents.get(norm_path(member.linkname), b"") if member.islnk() else contents.get(path, b"")
            base = path.rsplit("/", 1)[-1]
            if path.startswith("boot/vmlinuz") or base.startswith("vmlinuz"):
                kernel_out.clear()
                kernel_out.append(data)
                continue
            add_node(tree, path, FsNode("reg", 0o100000 | (mode or 0o644), data))


def overlay_text(tree: dict[str, FsNode], path: str, text: str, executable: bool = False) -> None:
    data = text.replace("\r\n", "\n").encode("utf-8")
    add_node(tree, path, FsNode("reg", 0o100755 if executable else 0o100644, data))


def cpio_pad(size: int) -> int:
    return (4 - (size % 4)) % 4


def write_cpio(tree: dict[str, FsNode], dest: Path) -> None:
    """Пишет cpio.gz потоково — образ с firmware/Firefox не влезает в один bytearray."""

    def sort_key(item: tuple[str, FsNode]) -> tuple:
        path, node = item
        return (path.count("/"), 0 if node.kind == "dir" else 1, path)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    inode = 1

    with gzip.GzipFile(filename="", mode="wb", fileobj=tmp.open("wb"), compresslevel=6, mtime=0) as gz:

        def emit(name: str, mode: int, body: bytes = b"", rmajor: int = 0, rminor: int = 0) -> None:
            nonlocal inode
            name_bytes = name.encode("utf-8") + b"\0"
            header = (
                f"{0o070701:06o}"
                f"{inode:08X}"
                f"{mode:08X}"
                f"{0:08X}{0:08X}{1:08X}"
                f"{int(time.time()) & 0xFFFFFFFF:08X}"
                f"{len(body):08X}"
                f"{0:08X}{0:08X}"
                f"{rmajor:08X}{rminor:08X}"
                f"{len(name_bytes):08X}"
                f"{0:08X}"
            ).encode("ascii")
            if len(header) != 110:
                raise RuntimeError(f"bad cpio header length {len(header)}")
            gz.write(header)
            gz.write(name_bytes)
            gz.write(b"\0" * cpio_pad(110 + len(name_bytes)))
            # крупные файлы — кусками (лимит WriteFile на Windows)
            view = memoryview(body)
            step = 8 * 1024 * 1024
            for off in range(0, len(view), step):
                gz.write(view[off : off + step])
            gz.write(b"\0" * cpio_pad(len(body)))
            inode += 1

        emit(".", stat.S_IFDIR | 0o755)
        for path, node in sorted(tree.items(), key=sort_key):
            if node.kind == "dir":
                emit(path, node.mode or (stat.S_IFDIR | 0o755))
            elif node.kind == "lnk":
                emit(path, node.mode or (stat.S_IFLNK | 0o777), node.data)
            elif node.kind == "chr":
                emit(path, node.mode or stat.S_IFCHR, rmajor=node.rmajor, rminor=node.rminor)
            elif node.kind == "blk":
                emit(path, node.mode or stat.S_IFBLK, rmajor=node.rmajor, rminor=node.rminor)
            elif node.kind == "fifo":
                emit(path, node.mode or stat.S_IFIFO)
            else:
                emit(path, node.mode or (stat.S_IFREG | 0o644), node.data)
        emit("TRAILER!!!", 0)

    if dest.exists():
        dest.unlink()
    tmp.replace(dest)


def find_qemu() -> Path:
    candidates = [
        Path(r"D:\DeepOS\tools\qemu\qemu-system-x86_64.exe"),
        Path(r"D:\OS\MillenniumOS\tools\qemu\qemu-system-x86_64.exe"),
        ROOT / "tools" / "qemu" / "qemu-system-x86_64.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError("qemu-system-x86_64.exe not found in DeepOS or MillenniumOS")


def bios_dir(qemu: Path) -> Path | None:
    for candidate in (qemu.parent / "share", qemu.parent.parent / "share" / "qemu"):
        if (candidate / "bios-256k.bin").is_file():
            return candidate.resolve()
    return None


def install_packages(tree: dict[str, FsNode], packages: list[dict], kernel_out: list[bytes]) -> None:
    for pkg in packages:
        filename = f"{pkg['P']}-{pkg['V']}.apk"
        dest = APK_CACHE / pkg["repo"] / filename
        download(f"{pkg['repo_base']}/{filename}", dest, expected=int(pkg.get("S") or 0) or None)
        payloads = gzip_payloads(dest.read_bytes())
        if not payloads:
            raise RuntimeError(f"no tar payload in {filename}")
        for payload in payloads:
            ingest_tar(tree, payload, kernel_out)
        log(f"  installed {pkg['P']}")


def read_sources() -> dict[str, bytes]:
    files = {
        "usr/src/gtos/main.cpp": (ROOT / "src" / "main.cpp").read_bytes(),
        "usr/src/gtos/Bridge.cpp": (ROOT / "src" / "Bridge.cpp").read_bytes(),
        "usr/src/gtos/Bridge.h": (ROOT / "src" / "Bridge.h").read_bytes(),
    }
    qml_root = ROOT / "qml"
    for path in qml_root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(qml_root).as_posix()
            files[f"usr/share/gtos/qml/{rel}"] = path.read_bytes().replace(b"\r\n", b"\n")
    return files


COMPILE_INIT = r"""#!/bin/sh
export PATH=/usr/lib/qt6/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PKG_CONFIG_PATH=/usr/lib/pkgconfig:/usr/lib/qt6/pkgconfig
if [ -x /bin/busybox ]; then
    /bin/busybox --install -s /bin >/dev/null 2>&1
fi
mkdir -p /proc /sys /dev /tmp /root
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null
mount -t tmpfs tmpfs /tmp
exec >/dev/ttyS0 2>&1
echo GTOS_COMPILE_START
cd /usr/src/gtos || { echo GTOS_NO_SRC; poweroff -f; }
MOC=/usr/lib/qt6/libexec/moc
echo "MOC=$MOC"
ls -l "$MOC" || echo MOC_MISSING
"$MOC" -o moc_Bridge.cpp Bridge.h
echo MOC_RC:$?
g++ -std=c++17 -O2 -fPIC -o /tmp/gt-shell \
    -I/usr/include/qt6 \
    -I/usr/include/qt6/QtCore \
    -I/usr/include/qt6/QtGui \
    -I/usr/include/qt6/QtQml \
    -I/usr/include/qt6/QtQuick \
    -DQT_NO_DEBUG -DQT_CORE_LIB -DQT_GUI_LIB -DQT_QML_LIB -DQT_QUICK_LIB \
    main.cpp Bridge.cpp moc_Bridge.cpp \
    -L/usr/lib -lQt6Quick -lQt6Qml -lQt6OpenGL -lQt6Gui -lQt6Network -lQt6Core
echo GPP_RC:$?
if [ ! -x /tmp/gt-shell ]; then
    echo GTOS_COMPILE_FAIL
    poweroff -f
fi
echo GTOS_BINARY_BEGIN
/bin/busybox base64 /tmp/gt-shell
echo
echo GTOS_BINARY_END
poweroff -f
"""

RUNTIME_INIT = r"""#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/lib/qt6/bin
export HOME=/root
export TERM=vt100
export TZ=GMT-4
if [ -x /bin/busybox ]; then
    /bin/busybox --install -s /bin
fi
mkdir -p /proc /sys /dev /tmp /run /root /var/log /etc /mnt /data
mount -t proc proc /proc
mount -t sysfs sysfs /sys
if ! mount -t devtmpfs devtmpfs /dev 2>/dev/null; then
    mount -t tmpfs tmpfs /dev
    mdev -s 2>/dev/null
fi
mkdir -p /dev/pts /dev/shm
mount -t devpts devpts /dev/pts 2>/dev/null
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /run
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp /tmp/.X11-unix
hostname gt-os
echo GTOS_BOOT $(uname -a) > /dev/ttyS0
MODROOT=/lib/modules/$(uname -r)
# modprobe сам тянет зависимости (на linux-lts ручной порядок ломался)
if [ -d "$MODROOT" ]; then
    if [ ! -f "$MODROOT/modules.dep" ] && [ ! -f "$MODROOT/modules.dep.gz" ]; then
        depmod -a >/tmp/depmod.err 2>&1 || true
        echo "GTOS_DEPMOD $?" > /dev/ttyS0
    fi
fi
load_mod() {
    name=$1
    if command -v modprobe >/dev/null 2>&1; then
        if modprobe "$name" >/tmp/modprobe.err 2>&1; then
            echo "GTOS_MOD $name ok" > /dev/ttyS0
            return 0
        fi
        echo "GTOS_MOD $name fail $(tr '\n' ' ' < /tmp/modprobe.err)" > /dev/ttyS0
        return 1
    fi
    echo "GTOS_MOD $name no-modprobe" > /dev/ttyS0
    return 1
}
# порядок: кольцо → virtio → pci → устройства; ФС; GPU; звук
load_mod virtio_ring
load_mod virtio
load_mod virtio_pci
load_mod virtio_blk
load_mod failover
load_mod net_failover
load_mod virtio_net
load_mod netfs
load_mod 9pnet
load_mod 9pnet_virtio
load_mod 9p
load_mod crc16
load_mod crc32c
load_mod mbcache
load_mod jbd2
load_mod ext4
load_mod scsi_mod
load_mod libata
load_mod ahci
load_mod ata_piix
load_mod nvme
load_mod usbcore
load_mod xhci_hcd
load_mod xhci_pci
load_mod ehci_hcd
load_mod ehci_pci
load_mod usb_storage
load_mod hid
load_mod usbhid
load_mod hid_generic
load_mod e1000
load_mod e1000e
load_mod r8169
load_mod cfg80211
load_mod mac80211
load_mod iwlwifi
load_mod drm
load_mod drm_kms_helper
load_mod drm_shmem_helper
load_mod drm_ttm_helper
load_mod ttm
load_mod virtio_dma_buf
load_mod virtio_gpu
load_mod i915
load_mod amdgpu
load_mod evdev
load_mod soundcore
load_mod snd
load_mod snd_hda_intel
echo "GTOS_DRI $(ls /dev/dri 2>&1 | tr '\n' ' ')" > /dev/ttyS0
if [ -x /sbin/udevd ]; then
    /sbin/udevd --daemon >>/var/log/udev.log 2>&1
    udevadm trigger --action=add >>/var/log/udev.log 2>&1
    udevadm settle --timeout=6 >>/var/log/udev.log 2>&1
elif command -v mdev >/dev/null 2>&1; then
    mdev -s
fi
# Постоянный том: LABEL установки → разделы → целый диск → 9p
mount_persist() {
    mkdir -p /data
    if command -v blkid >/dev/null 2>&1; then
        for lab in GTOSROOT GTOSDATA; do
            dev=$(blkid -L "$lab" 2>/dev/null) || true
            if [ -n "$dev" ] && [ -b "$dev" ]; then
                if mount -t ext4 "$dev" /data 2>/tmp/mnt.err; then
                    echo "GTOS_PERSIST label:$lab:$dev" > /dev/ttyS0
                    return 0
                fi
            fi
        done
    fi
    for tag in gtoshome gtosdata; do
        if mount -t 9p -o trans=virtio,version=9p2000.L "$tag" /data 2>/tmp/9p.err; then
            echo "GTOS_PERSIST 9p:$tag" > /dev/ttyS0
            return 0
        fi
    done
    for disk in /dev/vda2 /dev/vdb2 /dev/sda2 /dev/nvme0n1p2 /dev/vda /dev/vdb /dev/sda /dev/nvme0n1; do
        [ -b "$disk" ] || continue
        if mount -t ext4 "$disk" /data 2>/tmp/mnt.err; then
            echo "GTOS_PERSIST ext4:$disk" > /dev/ttyS0
            return 0
        fi
    done
    # только в QEMU: форматнуть пустой virtio-диск данных
    for disk in /dev/vdb /dev/vda; do
        [ -b "$disk" ] || continue
        if command -v mkfs.ext4 >/dev/null 2>&1; then
            mkfs.ext4 -F -L GTOSDATA "$disk" >/tmp/mkfs.err 2>&1
            if mount -t ext4 "$disk" /data 2>/tmp/mnt2.err; then
                echo "GTOS_PERSIST formatted:$disk" > /dev/ttyS0
                return 0
            fi
        fi
    done
    echo "GTOS_PERSIST none" > /dev/ttyS0
    return 1
}
if mount_persist; then
    mkdir -p /data/home /data/gtos /data/var
    mkdir -p /home /var/lib/gtos
    # После qemu-img resize дорастаем ext4 до полного размера диска (онлайн)
    SRC=$(awk '$2=="/data"{print $1; exit}' /proc/mounts 2>/dev/null || true)
    if [ -n "$SRC" ] && command -v resize2fs >/dev/null 2>&1; then
        resize2fs "$SRC" >/tmp/resize2fs.log 2>&1 || true
        echo "GTOS_RESIZE $SRC" > /dev/ttyS0
    fi
    mount --bind /data/home /home 2>/dev/null || true
    mount --bind /data/gtos /var/lib/gtos 2>/dev/null || true
    echo ready > /var/lib/gtos/persist-ready
fi
# Сеть: ethernet DHCP + подготовка Wi‑Fi
ip link set lo up 2>/dev/null
NET_OK=0
for iface in eth0 ens3 enp0s3 enp0s8 eno1 enp1s0; do
    if [ -d /sys/class/net/$iface ]; then
        ip link set "$iface" up 2>/dev/null
        if command -v dhcpcd >/dev/null 2>&1; then
            dhcpcd -q "$iface" >/tmp/dhcp.log 2>&1 &
        elif command -v udhcpc >/dev/null 2>&1; then
            udhcpc -i "$iface" -n -q -t 3 -T 2 >/tmp/dhcp.log 2>&1 &
        fi
        echo "GTOS_NET $iface" > /dev/ttyS0
        NET_OK=1
        break
    fi
done
for wiface in wlan0 wlp1s0 wlp2s0 wlp3s0; do
    if [ -d /sys/class/net/$wiface ]; then
        ip link set "$wiface" up 2>/dev/null || true
        echo "GTOS_WIFI $wiface" > /dev/ttyS0
        mkdir -p /var/lib/gtos
        printf '%s\n' "$wiface" > /var/lib/gtos/wifi-iface
        break
    fi
done
if command -v alsactl >/dev/null 2>&1; then
    alsactl init >/tmp/alsa.log 2>&1 || true
    echo GTOS_ALSA > /dev/ttyS0
fi
if [ -f /etc/ssl/certs/ca-certificates.crt ] || [ -d /etc/ssl/certs ]; then
    echo GTOS_TLS_OK > /dev/ttyS0
fi
echo GTOS_GUI_START > /dev/ttyS0
if [ -x /usr/bin/xinit ] && [ -x /usr/bin/gtos-session ]; then
    xinit /usr/bin/gtos-session -- :0 vt1 -nolisten tcp -noreset >/var/log/xinit.log 2>&1 &
    xpid=$!
    (
        sleep 12
        echo GTOS_XORG_TAIL
        tail -n 50 /var/log/Xorg.0.log 2>/dev/null
        echo GTOS_SESSION_TAIL
        tail -n 50 /var/log/gtos.log 2>/dev/null
        echo GTOS_NET_TAIL
        ip addr 2>/dev/null | head -n 40
        mount | grep -E 'data|home|gtos' | head -n 10
    ) > /dev/ttyS0 2>&1 &
    wait "$xpid"
    echo GTOS_GUI_EXIT $? > /dev/ttyS0
    sync
    echo GTOS_GTOS_LOG > /dev/ttyS0
    cat /var/log/gtos.log > /dev/ttyS0 2>/dev/null
    echo GTOS_XORG_EE > /dev/ttyS0
    grep -E '\(EE\)|\(WW\)|Fatal|failed' /var/log/Xorg.0.log 2>/dev/null | head -n 40 > /dev/ttyS0
    umount /home 2>/dev/null
    umount /var/lib/gtos 2>/dev/null
    umount /data 2>/dev/null
    echo GTOS_XINIT_LOG > /dev/ttyS0
    tail -n 40 /var/log/xinit.log > /dev/ttyS0 2>/dev/null
fi
echo GTOS_SHELL
exec /bin/sh -l </dev/console >/dev/console 2>&1
"""

SESSION = r"""#!/bin/sh
export DISPLAY=:0
export PATH=/usr/lib/qt6/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TZ=GMT-4
export QT_QPA_PLATFORM=xcb
# Безопасный режим: gtos.safemode=1 в cmdline или флаг request-safemode
SAFEMODE=0
if grep -qw 'gtos.safemode=1' /proc/cmdline 2>/dev/null || grep -qw 'gtos.safemode' /proc/cmdline 2>/dev/null; then
    SAFEMODE=1
fi
mkdir -p /run /var/lib/gtos
if [ -f /var/lib/gtos/request-safemode ]; then
    SAFEMODE=1
    rm -f /var/lib/gtos/request-safemode
fi
if [ "$SAFEMODE" = 1 ]; then
    touch /run/gtos-safemode /var/lib/gtos/safemode
    echo GTOS_SAFEMODE 1 > /dev/ttyS0
else
    rm -f /run/gtos-safemode /var/lib/gtos/safemode
    echo GTOS_SAFEMODE 0 > /dev/ttyS0
fi
export GTOS_SAFEMODE=$SAFEMODE
# Масштаб UI (HiDPI) — Параметры → Питание/экран или /var/lib/gtos/ui-scale
UI_SCALE=$(cat /var/lib/gtos/ui-scale 2>/dev/null | tr -d '\r\n' | head -n1)
case "$UI_SCALE" in
    1|1.0|1.25|1.5|2|2.0) ;;
    *) UI_SCALE=1 ;;
esac
export QT_SCALE_FACTOR="$UI_SCALE"
export QT_AUTO_SCREEN_SCALE_FACTOR=0
echo "GTOS_UI_SCALE $UI_SCALE" > /dev/ttyS0
# Звук по умолчанию: unmute + разумная громкость
if command -v amixer >/dev/null 2>&1; then
    amixer -q set Master unmute 80% 2>/dev/null || true
    amixer -q sset Master 80% unmute 2>/dev/null || true
    amixer -q set PCM unmute 80% 2>/dev/null || true
    amixer -q set Speaker unmute 2>/dev/null || true
    amixer -q set Headphone unmute 2>/dev/null || true
    echo GTOS_AUDIO_DEFAULT > /dev/ttyS0
fi
# GPU только на реальном железе. QEMU virtio-gpu без VirGL даёт
# «virtio_gpu: driver missing» и роняет Qt Quick — там software.
USE_GPU=0
drm_drv=""
if [ -e /dev/dri/card0 ] || [ -e /dev/dri/renderD128 ]; then
    if [ -L /sys/class/drm/card0/device/driver ]; then
        drm_drv=$(basename "$(readlink -f /sys/class/drm/card0/device/driver)" 2>/dev/null || true)
    fi
    case "$drm_drv" in
        i915|amdgpu|radeon|nouveau|xe) USE_GPU=1 ;;
        *) USE_GPU=0 ;;
    esac
fi
if [ "$USE_GPU" = 1 ]; then
    unset QT_QUICK_BACKEND QSG_RHI_BACKEND LIBGL_ALWAYS_SOFTWARE QT_OPENGL 2>/dev/null
    export QSG_RENDER_LOOP=threaded
    echo "GTOS_RENDER gpu:$drm_drv" > /dev/ttyS0
else
    export QT_QUICK_BACKEND=software
    export QSG_RHI_BACKEND=software
    export QSG_RENDER_LOOP=basic
    export LIBGL_ALWAYS_SOFTWARE=1
    export QT_OPENGL=software
    export QT_XCB_GL_INTEGRATION=none
    export LIBGL_DRIVERS_PATH=/usr/lib/dri
    echo "GTOS_RENDER software:${drm_drv:-none}" > /dev/ttyS0
fi
export QSG_NO_VSYNC=1
export QSG_INFO=0
export QT_LOGGING_RULES='*.debug=false'
export QT_QPA_FONTDIR=/usr/share/fonts/dejavu
export QT_PLUGIN_PATH=/usr/lib/qt6/plugins
export QML_IMPORT_PATH=/usr/lib/qt6/qml
export QML2_IMPORT_PATH=/usr/lib/qt6/qml
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
export XDG_RUNTIME_DIR=/tmp/runtime-gtos
mkdir -p "$XDG_RUNTIME_DIR" /tmp /tmp/.X11-unix /root /var/lib/gtos /home/misha
chmod 700 "$XDG_RUNTIME_DIR"
chmod 1777 /tmp /tmp/.X11-unix 2>/dev/null || true
hostname gt-os
printf '%s\n' gt-os > /etc/hostname
if ! grep -q '^misha:' /etc/passwd 2>/dev/null; then
    echo 'misha:x:1000:1000:Misha:/home/misha:/bin/sh' >> /etc/passwd
fi
if ! grep -q '^misha:' /etc/group 2>/dev/null; then
    echo 'misha:x:1000:' >> /etc/group
fi
mkdir -p /home/misha/Документы /home/misha/Загрузки /home/misha/Изображения /home/misha/Музыка /home/misha/Видео '/home/misha/Рабочий стол' /home/misha/Проекты /home/misha/Архив /home/misha/.Корзина /home/misha/.config/gtos
# Демо-файлы только при первом создании дома
if [ ! -f /home/misha/Документы/добро_пожаловать.txt ]; then
    printf '%s\n' 'Добро пожаловать в GT/OS 1.1 — повседневный рабочий стол.' 'Файлы и настройки сохраняются на постоянном томе.' > /home/misha/Документы/добро_пожаловать.txt
fi
if [ ! -f /home/misha/Проекты/readme.txt ]; then
    printf '%s\n' 'Проекты GT/OS 1.1' > /home/misha/Проекты/readme.txt
fi
chown -R 1000:1000 /home/misha 2>/dev/null || true
printf '%s\n' 1.6 > /var/lib/gtos/version
# Репозитории Alpine для магазина (установка пакетов из сети)
mkdir -p /etc/apk /var/lib/gtos/apk-cache
BRANCH=v3.24
if [ -f /var/lib/gtos/alpine-branch ]; then
    BRANCH=$(tr -d '\r\n' < /var/lib/gtos/alpine-branch)
fi
[ -n "$BRANCH" ] || BRANCH=v3.24
printf '%s\n' \
    "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/main" \
    "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/community" \
    > /etc/apk/repositories
# Пользователя создаёт оболочка (мастер первого входа), если username ещё нет
if [ -f /var/lib/gtos/username ]; then
    U=$(cat /var/lib/gtos/username 2>/dev/null | tr -d '\r\n')
else
    U=misha
fi
[ -n "$U" ] || U=misha
export HOME=/home/$U
export USER=$U
export LOGNAME=$U
mkdir -p "$HOME"
xsetroot -solid "#07080d" 2>/dev/null
xsetroot -cursor_name left_ptr 2>/dev/null
# GUI-приложения (Firefox) идут от пользователя, не от root
xhost +SI:localuser:misha >/dev/null 2>&1 || xhost +local: >/dev/null 2>&1 || true
xhost +SI:localuser:$U >/dev/null 2>&1 || true
# Раскладка X11: русский по умолчанию (переключение из панели GT/OS)
if ! command -v setxkbmap >/dev/null 2>&1 || [ ! -d /usr/share/X11/xkb/symbols ]; then
    for _i in 1 2 3 4 5 6 7 8; do
        ping -c 1 -W 1 1.1.1.1 >/dev/null 2>&1 && break
        sleep 1
    done
    apk update --cache-dir /var/lib/gtos/apk-cache >/tmp/apk-xkb.log 2>&1 || true
    apk add --no-progress --cache-dir /var/lib/gtos/apk-cache setxkbmap xkeyboard-config >>/tmp/apk-xkb.log 2>&1 || true
fi
ILANG=ru
if [ -f /var/lib/gtos/input-lang ]; then
    ILANG=$(tr -d '\r\n' < /var/lib/gtos/input-lang)
fi
[ "$ILANG" = "en" ] || ILANG=ru
printf '%s\n' "$ILANG" > /var/lib/gtos/input-lang
if command -v setxkbmap >/dev/null 2>&1; then
    setxkbmap -layout "$ILANG" >/tmp/xkb.log 2>&1 || setxkbmap "$ILANG" >>/tmp/xkb.log 2>&1 || true
    echo "GTOS_XKB $ILANG" > /dev/ttyS0
else
    echo "GTOS_XKB missing" > /dev/ttyS0
fi
# Openbox даёт titlebar/крестики внешним X11-окнам (у gt-shell fullscreen — без рамки)
if ! command -v openbox >/dev/null 2>&1; then
    for _i in 1 2 3 4 5 6 7 8; do
        ping -c 1 -W 1 1.1.1.1 >/dev/null 2>&1 && break
        sleep 1
    done
    apk update --cache-dir /var/lib/gtos/apk-cache >/tmp/apk-openbox.log 2>&1 || true
    apk add --no-progress --cache-dir /var/lib/gtos/apk-cache openbox >>/tmp/apk-openbox.log 2>&1 || true
fi
# bluez для Параметры → Bluetooth (в QEMU адаптера может не быть — UI честно скажет)
if ! command -v bluetoothctl >/dev/null 2>&1; then
    apk update --cache-dir /var/lib/gtos/apk-cache >/tmp/apk-bluez.log 2>&1 || true
    apk add --no-progress --cache-dir /var/lib/gtos/apk-cache bluez bluez-openrc >>/tmp/apk-bluez.log 2>&1 || true
fi
# запасной apk, если пакеты не попали в образ
for _need in pdftoppm:poppler-utils xclip:xclip dunst:dunst cupsd:cups; do
    _bin=${_need%%:*}; _pkg=${_need##*:}
    if ! command -v "$_bin" >/dev/null 2>&1 && [ ! -x "/usr/sbin/$_bin" ]; then
        apk update --cache-dir /var/lib/gtos/apk-cache >/tmp/apk-extra.log 2>&1 || true
        apk add --no-progress --cache-dir /var/lib/gtos/apk-cache "$_pkg" >>/tmp/apk-extra.log 2>&1 || true
    fi
done
# D-Bus + невидимый dunst → inbox шторки GT/OS
mkdir -p /var/lib/gtos /run/dbus /etc/dunst
if [ -f /usr/share/gtos/dunst.conf ]; then
    cp -f /usr/share/gtos/dunst.conf /etc/dunst/dunstrc
fi
if command -v dbus-daemon >/dev/null 2>&1; then
    if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
        eval $(dbus-launch --sh-syntax 2>/tmp/dbus-launch.log) || true
        export DBUS_SESSION_BUS_ADDRESS
        export DBUS_SESSION_BUS_PID
    fi
    echo "GTOS_DBUS ${DBUS_SESSION_BUS_ADDRESS:-none}" > /dev/ttyS0
fi
if command -v dunst >/dev/null 2>&1; then
    dunst -config /etc/dunst/dunstrc >/tmp/dunst.log 2>&1 &
    echo GTOS_NOTIFY dunst > /dev/ttyS0
fi
# CUPS / Wi‑Fi автоподъём — не в безопасном режиме
if [ "$SAFEMODE" != 1 ]; then
    if command -v cupsd >/dev/null 2>&1 || [ -x /usr/sbin/cupsd ]; then
        mkdir -p /var/run/cups /var/spool/cups /var/cache/cups /etc/cups
        /usr/sbin/cupsd >/tmp/cupsd.log 2>&1 &
        echo GTOS_CUPS on > /dev/ttyS0
    fi
    if [ -f /var/lib/gtos/wpa_supplicant.conf ] && command -v wpa_supplicant >/dev/null 2>&1; then
        IFACE=$(iwconfig 2>/dev/null | awk '/^[a-z]/{print $1; exit}')
        [ -z "$IFACE" ] && IFACE=$(ls /sys/class/net 2>/dev/null | grep -E '^wl|^wlan' | head -n1)
        if [ -n "$IFACE" ]; then
            ip link set "$IFACE" up 2>/dev/null || true
            killall wpa_supplicant 2>/dev/null || true
            wpa_supplicant -B -i "$IFACE" -c /var/lib/gtos/wpa_supplicant.conf >/tmp/wpa-boot.log 2>&1 || true
            ( sleep 2; udhcpc -i "$IFACE" -n -q -t 5 >/tmp/dhcp-wifi-boot.log 2>&1 ) &
            echo "GTOS_WIFI_BOOT $IFACE" > /dev/ttyS0
        fi
    fi
else
    echo GTOS_CUPS skip > /dev/ttyS0
    echo GTOS_WIFI_BOOT skip > /dev/ttyS0
fi
if command -v openbox >/dev/null 2>&1; then
    mkdir -p /etc/xdg/openbox /root/.config/openbox
    # Всегда ставим тему GT/OS — те же цвета, что у QML titleBar (#2d2d2d)
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
        '<openbox_config xmlns="http://openbox.org/3.4/rc">' \
        '<theme><name>GTOS</name><titleLayout>NLIMC</titleLayout><keepBorder>yes</keepBorder><animateIconify>no</animateIconify></theme>' \
        '<desktops><number>1</number><firstdesk>1</firstdesk><popupTime>0</popupTime></desktops>' \
        '<keyboard/><mouse/><applications/>' \
        '</openbox_config>' \
        > /etc/xdg/openbox/rc.xml
    cp -f /etc/xdg/openbox/rc.xml /root/.config/openbox/rc.xml 2>/dev/null || true
    openbox >/tmp/openbox.log 2>&1 &
    echo GTOS_WM openbox > /dev/ttyS0
else
    echo GTOS_WM none > /dev/ttyS0
    echo GTOS_WM_LOG $(tr '\n' ' ' < /tmp/apk-openbox.log 2>/dev/null | cut -c1-200) > /dev/ttyS0
fi
echo GTOS_SESSION_1_2 > /dev/ttyS0
# Перезапуск оболочки при падении (0 = штатный выход)
GT_SHELL=/usr/bin/gt-shell
while true; do
    if command -v stdbuf >/dev/null 2>&1; then
        stdbuf -oL -eL "$GT_SHELL" >>/var/log/gtos.log 2>&1
    else
        "$GT_SHELL" >>/var/log/gtos.log 2>&1
    fi
    ec=$?
    echo "GTOS_SHELL_EXIT $ec" > /dev/ttyS0
    if [ "$ec" -eq 0 ]; then
        break
    fi
    echo "GTOS_SHELL_RESPAWN" > /dev/ttyS0
    sleep 1
done
"""

XORG = """Section "Module"
    Disable "glx"
EndSection
Section "Device"
    Identifier "GTOS"
    Driver "modesetting"
    Option "AccelMethod" "none"
    Option "DRI" "false"
    Option "ShadowFB" "true"
EndSection
Section "Screen"
    Identifier "Screen0"
    Device "GTOS"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080" "1600x900" "1366x768" "1280x720"
    EndSubSection
EndSection
Section "ServerFlags"
    Option "AutoAddDevices" "true"
    Option "AllowMouseOpenFail" "true"
    Option "DontZap" "false"
EndSection
"""


def add_common_overlay(tree: dict[str, FsNode], kernel_version: str) -> None:
    overlay_text(
        tree,
        "etc/os-release",
        f"""NAME="GT/OS"
VERSION="{GTOS_VERSION}"
ID=gtos
ID_LIKE=alpine
PRETTY_NAME="GT/OS {GTOS_VERSION}"
VERSION_ID={GTOS_VERSION}
VARIANT="Desktop"
VARIANT_ID=desktop
GTOS_KERNEL={kernel_version}
""",
    )
    overlay_text(tree, "etc/hostname", "gtos\n")
    overlay_text(
        tree,
        "etc/X11/Xwrapper.config",
        "allowed_users=anybody\nneeds_root_rights=yes\n",
    )
    overlay_text(tree, "etc/X11/xorg.conf", XORG)
    overlay_text(tree, "usr/bin/gtos-session", SESSION, executable=True)
    install_sh = (ROOT / "scripts" / "gtos-install.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-install", install_sh, executable=True)
    shell_upd = (ROOT / "scripts" / "gtos-shell-update.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-shell-update", shell_upd, executable=True)
    hwcheck = (ROOT / "scripts" / "gtos-hwcheck.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-hwcheck", hwcheck, executable=True)
    notifyd = (ROOT / "scripts" / "gtos-notifyd.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-notifyd", notifyd, executable=True)
    store_inst = (ROOT / "scripts" / "gtos-store-install.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-store-install", store_inst, executable=True)
    dunst_cfg = (ROOT / "scripts" / "gtos-dunst.conf").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/share/gtos/dunst.conf", dunst_cfg)
    overlay_text(tree, "etc/dunst/dunstrc", dunst_cfg)
    overlay_text(tree, "usr/share/gtos/version", "1.6\n")
    overlay_text(tree, "boot/gtos-version", "1.6\n")
    # канал обновлений по умолчанию (можно переопределить в /var/lib/gtos/update-channel)
    overlay_text(tree, "usr/share/gtos/update-channel.example", "url=\n# пример: url=https://example.com/gtos/\n")
    runuser_sh = (ROOT / "scripts" / "gtos-runuser.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-runuser", runuser_sh, executable=True)
    firefox_sh = (ROOT / "scripts" / "gtos-firefox.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-firefox", firefox_sh, executable=True)
    sources = read_sources()
    for path, data in sources.items():
        add_node(tree, path, FsNode("reg", 0o100644, data.replace(b"\r\n", b"\n")))
    # обои рабочего стола / экрана блокировки
    assets = ROOT / "assets"
    wall = assets / "wallpaper.jpg"
    if wall.is_file():
        add_node(tree, "usr/share/gtos/wallpaper.jpg", FsNode("reg", 0o100644, wall.read_bytes()))
    lock_wall = assets / "lock-wallpaper.jpg"
    if lock_wall.is_file():
        add_node(tree, "usr/share/gtos/lock-wallpaper.jpg", FsNode("reg", 0o100644, lock_wall.read_bytes()))
    for i in range(1, 5):
        extra = assets / f"wallpaper-{i}.jpg"
        if extra.is_file():
            add_node(tree, f"usr/share/gtos/wallpaper-{i}.jpg", FsNode("reg", 0o100644, extra.read_bytes()))
    if "bin/sh" not in tree and "bin/busybox" in tree:
        add_node(tree, "bin/sh", FsNode("lnk", 0o120777, b"busybox"))


def run_compile(qemu: Path, kernel: Path, initrd: Path) -> bytes:
    log_path = OUT / "compile-serial.log"
    if log_path.exists():
        log_path.unlink()
    args = [
        "-accel", "tcg,thread=multi",
        "-cpu", "qemu64",
        "-m", "4096",
        "-smp", "4",
        "-kernel", str(kernel),
        "-initrd", str(initrd),
        "-append", "console=ttyS0,115200 rdinit=/init loglevel=1 panic=1",
        "-display", "none",
        "-serial", f"file:{log_path}",
        "-no-reboot",
    ]
    bios = bios_dir(qemu)
    if bios is not None:
        args = ["-L", str(bios), *args]
    log(f"compile in QEMU: {qemu}")
    proc = subprocess.Popen([str(qemu), *args])
    deadline = time.time() + 900
    data = b""
    while time.time() < deadline:
        if log_path.exists():
            data = log_path.read_bytes()
            if b"GTOS_BINARY_END" in data or b"GTOS_COMPILE_FAIL" in data or b"Kernel panic" in data:
                break
        if proc.poll() is not None and log_path.exists():
            data = log_path.read_bytes()
            if b"GTOS_BINARY_END" in data or b"GTOS_COMPILE_FAIL" in data:
                break
        time.sleep(2)
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=30)
    text = data.decode("utf-8", "replace")
    if b"GTOS_BINARY_END" not in data:
        tail = "\n".join(text.splitlines()[-80:])
        raise RuntimeError("shell compiler did not finish\n" + tail)
    match = re.search(r"GTOS_BINARY_BEGIN\s*(.*?)\s*GTOS_BINARY_END", text, re.S)
    if not match:
        raise RuntimeError("binary markers missing")
    blob = base64.b64decode(re.sub(r"\s+", "", match.group(1)))
    if not blob.startswith(b"\x7fELF"):
        raise RuntimeError("compiler output is not an ELF binary")
    log(f"gt-shell {len(blob)} bytes")
    return blob


def main() -> int:
    log("GT/OS build")
    branch = detect_branch()
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{branch}"
    log(f"Alpine {branch}")
    by_name, providers = load_indexes(branch_root)
    runtime = resolve(by_name, providers, RUNTIME_PACKAGES)
    build_pkgs = resolve(by_name, providers, COMPILE_PACKAGES + BUILD_EXTRA)
    kernel_version = by_name.get("linux-lts", {}).get("V") or by_name.get("linux-virt", {}).get("V", "linux")
    log(f"runtime packages: {len(runtime)}; compile packages: {len(build_pkgs)}; kernel {kernel_version}")

    build_tree: dict[str, FsNode] = {}
    compile_kernel: list[bytes] = []
    install_packages(build_tree, build_pkgs, compile_kernel)
    if not compile_kernel or b"HdrS" not in compile_kernel[-1][:1024]:
        raise RuntimeError("linux-virt (compile) did not contain a Linux bzImage")
    add_common_overlay(build_tree, kernel_version)
    overlay_text(build_tree, "init", COMPILE_INIT, executable=True)

    OUT.mkdir(parents=True, exist_ok=True)
    compile_vmlinuz = OUT / "vmlinuz-compile"
    compile_vmlinuz.write_bytes(compile_kernel[-1])
    compile_initrd = OUT / "gtos-compile.cpio.gz"
    log("pack compiler initramfs")
    write_cpio(build_tree, compile_initrd)
    log(f"compiler initrd {compile_initrd.stat().st_size} bytes")

    qemu = find_qemu()
    binary = run_compile(qemu, compile_vmlinuz, compile_initrd)

    runtime_tree: dict[str, FsNode] = {}
    kernel_out: list[bytes] = []
    install_packages(runtime_tree, runtime, kernel_out)
    if not kernel_out or b"HdrS" not in kernel_out[-1][:1024]:
        raise RuntimeError("linux-lts did not contain a Linux bzImage")
    kernel_path = OUT / "vmlinuz"
    kernel_path.write_bytes(kernel_out[-1])
    add_common_overlay(runtime_tree, kernel_version)
    add_node(runtime_tree, "usr/bin/gt-shell", FsNode("reg", 0o100755, binary))
    # ядро для установщика (initrd берётся с ISO /boot)
    add_node(runtime_tree, "usr/share/gtos/boot/vmlinuz", FsNode("reg", 0o100644, kernel_out[-1]))
    overlay_text(runtime_tree, "init", RUNTIME_INIT, executable=True)
    initrd_path = OUT / "gtos-rootfs.cpio.gz"
    log("pack runtime initramfs")
    write_cpio(runtime_tree, initrd_path)
    log(f"kernel {kernel_path.stat().st_size} bytes")
    log(f"initrd {initrd_path.stat().st_size} bytes")
    log("GT/OS image is ready")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        log(f"error: {exc}")
        sys.exit(1)
