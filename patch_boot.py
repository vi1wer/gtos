#!/usr/bin/env python3
"""Push the current init script and Xorg config into the initramfs."""

from build import XORG, RUNTIME_INIT, SESSION, FsNode
from refresh_ui import parse_cpio
from build import write_cpio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INITRD = ROOT / "out" / "gtos-rootfs.cpio.gz"

import gzip

tree = parse_cpio(gzip.open(INITRD, "rb").read())
tree["init"] = FsNode("reg", 0o100755, RUNTIME_INIT.replace("\r\n", "\n").encode())
tree["etc/X11/xorg.conf"] = FsNode("reg", 0o100644, XORG.replace("\r\n", "\n").encode())
tree["usr/bin/gtos-session"] = FsNode("reg", 0o100755, SESSION.replace("\r\n", "\n").encode())
qml = (ROOT / "qml" / "Main.qml").read_bytes().replace(b"\r\n", b"\n")
wall = (ROOT / "assets" / "wallpaper.jpg").read_bytes()
tree["usr/share/gtos/qml/Main.qml"] = FsNode("reg", 0o100644, qml)
tree["usr/share/gtos/wallpaper.jpg"] = FsNode("reg", 0o100644, wall)
write_cpio(tree, INITRD)
print("patched", INITRD.stat().st_size)
