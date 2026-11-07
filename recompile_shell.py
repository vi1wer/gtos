#!/usr/bin/env python3
"""Recompile gt-shell and inject it into the runtime initrd."""

from __future__ import annotations

import gzip
from pathlib import Path

from build import (
    OUT,
    ROOT,
    FsNode,
    find_qemu,
    run_compile,
    write_cpio,
)
from refresh_ui import parse_cpio

COMPILE_INITRD = OUT / "gtos-compile.cpio.gz"
RUNTIME = OUT / "gtos-rootfs.cpio.gz"


def main() -> int:
    if not COMPILE_INITRD.is_file():
        raise SystemExit("нет out/gtos-compile.cpio.gz — сначала python build.py")
    if not (OUT / "vmlinuz").is_file():
        raise SystemExit("нет out/vmlinuz")

    tree = parse_cpio(gzip.open(COMPILE_INITRD, "rb").read())
    for name in ("main.cpp", "Bridge.cpp", "Bridge.h"):
        data = (ROOT / "src" / name).read_bytes().replace(b"\r\n", b"\n")
        tree[f"usr/src/gtos/{name}"] = FsNode("reg", 0o100644, data)
    write_cpio(tree, COMPILE_INITRD)
    print("updated compile initrd sources")

    qemu = find_qemu()
    binary = run_compile(qemu, OUT / "vmlinuz", COMPILE_INITRD)
    (OUT / "gt-shell").write_bytes(binary)

    runtime = parse_cpio(gzip.open(RUNTIME, "rb").read())
    runtime["usr/bin/gt-shell"] = FsNode("reg", 0o100755, binary)
    qml = (ROOT / "qml" / "Main.qml").read_bytes().replace(b"\r\n", b"\n")
    runtime["usr/share/gtos/qml/Main.qml"] = FsNode("reg", 0o100644, qml)
    write_cpio(runtime, RUNTIME)
    print("runtime updated", RUNTIME.stat().st_size, "gt-shell", len(binary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
