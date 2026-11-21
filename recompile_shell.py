#!/usr/bin/env python3
"""Recompile gt-shell and inject it into the runtime initrd."""

from __future__ import annotations

import gzip
from pathlib import Path

from build import (
    BUILD_EXTRA,
    COMPILE_INIT,
    COMPILE_PACKAGES,
    OUT,
    ROOT,
    FsNode,
    add_common_overlay,
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

COMPILE_INITRD = OUT / "gtos-compile.cpio.gz"
COMPILE_KERNEL = OUT / "vmlinuz-compile"
RUNTIME = OUT / "gtos-rootfs.cpio.gz"


def build_compile_initrd() -> None:
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{detect_branch()}"
    by_name, providers = load_indexes(branch_root)
    pkgs = resolve(by_name, providers, COMPILE_PACKAGES + BUILD_EXTRA)
    kernel_version = by_name.get("linux-virt", {}).get("V", "linux")
    tree: dict[str, FsNode] = {}
    kernel: list[bytes] = []
    install_packages(tree, pkgs, kernel)
    if not kernel or b"HdrS" not in kernel[-1][:1024]:
        raise SystemExit("linux-virt (compile) не дал bzImage")
    add_common_overlay(tree, kernel_version)
    overlay_text(tree, "init", COMPILE_INIT, executable=True)
    COMPILE_KERNEL.write_bytes(kernel[-1])
    write_cpio(tree, COMPILE_INITRD)
    print("built compile initrd", COMPILE_INITRD.stat().st_size)


def main() -> int:
    if not COMPILE_INITRD.is_file() or not COMPILE_KERNEL.is_file():
        build_compile_initrd()

    tree = parse_cpio(gzip.open(COMPILE_INITRD, "rb").read())
    for name in ("main.cpp", "Bridge.cpp", "Bridge.h"):
        data = (ROOT / "src" / name).read_bytes().replace(b"\r\n", b"\n")
        tree[f"usr/src/gtos/{name}"] = FsNode("reg", 0o100644, data)
    write_cpio(tree, COMPILE_INITRD)
    print("updated compile initrd sources")

    qemu = find_qemu()
    binary = run_compile(qemu, COMPILE_KERNEL, COMPILE_INITRD)
    (OUT / "gt-shell").write_bytes(binary)

    runtime = parse_cpio(gzip.open(RUNTIME, "rb").read())
    runtime["usr/bin/gt-shell"] = FsNode("reg", 0o100755, binary)
    for qml_file in (ROOT / "qml").glob("*.qml"):
        runtime[f"usr/share/gtos/qml/{qml_file.name}"] = FsNode(
            "reg", 0o100644, qml_file.read_bytes().replace(b"\r\n", b"\n"))
    write_cpio(runtime, RUNTIME)
    print("runtime updated", RUNTIME.stat().st_size, "gt-shell", len(binary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
