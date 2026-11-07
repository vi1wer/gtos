#!/usr/bin/env python3
"""Upgrade existing runtime initrd to GT/OS 1.1 without a full rebuild."""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

from build import (
    GTOS_VERSION,
    OUT,
    ROOT,
    RUNTIME_INIT,
    SESSION,
    XORG,
    FsNode,
    detect_branch,
    find_qemu,
    install_packages,
    load_indexes,
    overlay_text,
    resolve,
    run_compile,
    write_cpio,
)
from refresh_ui import parse_cpio

EXTRA_11 = [
    "iproute2",
    "iputils",
    "curl",
    "ca-certificates",
    "openssl",
    "e2fsprogs",
    "nano",
    "openssh-client",
    "sfdisk",
]


def main() -> int:
    runtime_path = OUT / "gtos-rootfs.cpio.gz"
    if not runtime_path.is_file():
        raise SystemExit("нет out/gtos-rootfs.cpio.gz — сначала python build.py")

    print(f"GT/OS -> {GTOS_VERSION}: patch runtime initrd")
    tree = parse_cpio(gzip.open(runtime_path, "rb").read())

    branch = detect_branch()
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{branch}"
    print(f"Alpine {branch}")
    by_name, providers = load_indexes(branch_root)
    pkgs = resolve(by_name, providers, EXTRA_11)
    print(f"inject packages: {len(pkgs)}")
    kernel_out: list[bytes] = []
    install_packages(tree, pkgs, kernel_out)

    kernel_version = by_name.get("linux-virt", {}).get("V", "linux")
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
    overlay_text(tree, "init", RUNTIME_INIT, executable=True)
    overlay_text(tree, "usr/bin/gtos-session", SESSION, executable=True)
    overlay_text(tree, "etc/X11/xorg.conf", XORG)
    install_sh = (ROOT / "scripts" / "gtos-install.sh").read_text(encoding="utf-8").replace("\r\n", "\n")
    overlay_text(tree, "usr/bin/gtos-install", install_sh, executable=True)
    # Installer payload: kernel only (initrd берётся с ISO/CD)
    vmlinuz = OUT / "vmlinuz"
    if vmlinuz.is_file():
        tree["usr/share/gtos/boot/vmlinuz"] = FsNode("reg", 0o100644, vmlinuz.read_bytes())
    qml = (ROOT / "qml" / "Main.qml").read_bytes().replace(b"\r\n", b"\n")
    wall = (ROOT / "assets" / "wallpaper.jpg").read_bytes()
    tree["usr/share/gtos/qml/Main.qml"] = FsNode("reg", 0o100644, qml)
    tree["usr/share/gtos/wallpaper.jpg"] = FsNode("reg", 0o100644, wall)

    # Пересборка gt-shell (Bridge timeout / исходники)
    compile_initrd = OUT / "gtos-compile.cpio.gz"
    if compile_initrd.is_file() and (OUT / "vmlinuz").is_file():
        print("recompile gt-shell…")
        ctree = parse_cpio(gzip.open(compile_initrd, "rb").read())
        for name in ("main.cpp", "Bridge.cpp", "Bridge.h"):
            data = (ROOT / "src" / name).read_bytes().replace(b"\r\n", b"\n")
            ctree[f"usr/src/gtos/{name}"] = FsNode("reg", 0o100644, data)
        write_cpio(ctree, compile_initrd)
        qemu = find_qemu()
        binary = run_compile(qemu, OUT / "vmlinuz", compile_initrd)
        (OUT / "gt-shell").write_bytes(binary)
        tree["usr/bin/gt-shell"] = FsNode("reg", 0o100755, binary)
        print(f"gt-shell {len(binary)} bytes")
    else:
        print("warning: нет compile initrd — оставляю старый gt-shell")

    write_cpio(tree, runtime_path)
    print(f"updated {runtime_path} ({runtime_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
