#!/usr/bin/env python3
"""Replace the QML shell and wallpaper inside the built initramfs."""

from __future__ import annotations

import gzip
import stat
from pathlib import Path

from build import FsNode, write_cpio

ROOT = Path(__file__).resolve().parent
INITRD = ROOT / "out" / "gtos-rootfs.cpio.gz"


def parse_cpio(blob: bytes) -> dict[str, FsNode]:
    tree: dict[str, FsNode] = {}
    off = 0
    while off + 110 <= len(blob):
        if blob[off : off + 6] not in (b"070701", b"070702"):
            break
        mode = int(blob[off + 14 : off + 22], 16)
        filesize = int(blob[off + 54 : off + 62], 16)
        rmajor = int(blob[off + 78 : off + 86], 16)
        rminor = int(blob[off + 86 : off + 94], 16)
        namesize = int(blob[off + 94 : off + 102], 16)
        name = blob[off + 110 : off + 110 + namesize - 1].decode("utf-8", "replace")
        header_end = off + 110 + namesize
        header_end += (4 - header_end % 4) % 4
        content = blob[header_end : header_end + filesize]
        data_end = header_end + filesize
        data_end += (4 - data_end % 4) % 4
        off = data_end
        if name in ("TRAILER!!!", "."):
            if name == "TRAILER!!!":
                break
            continue
        fmt = mode & 0o170000
        if fmt == stat.S_IFDIR:
            tree[name] = FsNode("dir", mode)
        elif fmt == stat.S_IFLNK:
            tree[name] = FsNode("lnk", mode, content)
        elif fmt == stat.S_IFCHR:
            tree[name] = FsNode("chr", mode, rmajor=rmajor, rminor=rminor)
        elif fmt == stat.S_IFBLK:
            tree[name] = FsNode("blk", mode, rmajor=rmajor, rminor=rminor)
        elif fmt == stat.S_IFIFO:
            tree[name] = FsNode("fifo", mode)
        else:
            tree[name] = FsNode("reg", mode, content)
    return tree


def main() -> None:
    raw = gzip.open(INITRD, "rb").read()
    tree = parse_cpio(raw)
    qml = (ROOT / "qml" / "Main.qml").read_bytes().replace(b"\r\n", b"\n")
    wall = (ROOT / "assets" / "wallpaper.jpg").read_bytes()
    lock_wall = ROOT / "assets" / "lock-wallpaper.jpg"
    tree["usr/share/gtos/qml/Main.qml"] = FsNode("reg", 0o100644, qml)
    tree["usr/share/gtos/wallpaper.jpg"] = FsNode("reg", 0o100644, wall)
    if lock_wall.is_file():
        tree["usr/share/gtos/lock-wallpaper.jpg"] = FsNode("reg", 0o100644, lock_wall.read_bytes())
    for i in range(1, 5):
        extra = ROOT / "assets" / f"wallpaper-{i}.jpg"
        if extra.is_file():
            tree[f"usr/share/gtos/wallpaper-{i}.jpg"] = FsNode("reg", 0o100644, extra.read_bytes())
    # site fonts (Sora / Syne / Montserrat / Cascadia) → OS + QT font dir
    fonts_dir = ROOT / "assets" / "fonts"
    tree["usr/share/fonts/gtos"] = FsNode("dir", 0o040755)
    tree["usr/share/gtos/fonts"] = FsNode("dir", 0o040755)
    if fonts_dir.is_dir():
        for fp in fonts_dir.iterdir():
            if fp.suffix.lower() in (".ttf", ".otf") and fp.stat().st_size > 1000:
                data = fp.read_bytes()
                tree[f"usr/share/fonts/gtos/{fp.name}"] = FsNode("reg", 0o100644, data)
                tree[f"usr/share/gtos/fonts/{fp.name}"] = FsNode("reg", 0o100644, data)
                # also beside DejaVu so QT_QPA_FONTDIR picks them up
                tree[f"usr/share/fonts/dejavu/{fp.name}"] = FsNode("reg", 0o100644, data)
    # session + xorg + init from build (эмулятор 1920×1080)
    from build import SESSION, XORG, RUNTIME_INIT
    tree["usr/bin/gtos-session"] = FsNode("reg", 0o100755, SESSION.encode().replace(b"\r\n", b"\n"))
    tree["etc/X11/xorg.conf"] = FsNode("reg", 0o100644, XORG.encode().replace(b"\r\n", b"\n"))
    tree["init"] = FsNode("reg", 0o100755, RUNTIME_INIT.encode().replace(b"\r\n", b"\n"))
    runuser = (ROOT / "scripts" / "gtos-runuser.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-runuser"] = FsNode("reg", 0o100755, runuser)
    ffwrap = (ROOT / "scripts" / "gtos-firefox.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-firefox"] = FsNode("reg", 0o100755, ffwrap)
    install_sh = (ROOT / "scripts" / "gtos-install.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-install"] = FsNode("reg", 0o100755, install_sh)
    shell_upd = (ROOT / "scripts" / "gtos-shell-update.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-shell-update"] = FsNode("reg", 0o100755, shell_upd)
    hwcheck = (ROOT / "scripts" / "gtos-hwcheck.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-hwcheck"] = FsNode("reg", 0o100755, hwcheck)
    notifyd = (ROOT / "scripts" / "gtos-notifyd.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-notifyd"] = FsNode("reg", 0o100755, notifyd)
    store_inst = (ROOT / "scripts" / "gtos-store-install.sh").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/bin/gtos-store-install"] = FsNode("reg", 0o100755, store_inst)
    dunst_cfg = (ROOT / "scripts" / "gtos-dunst.conf").read_bytes().replace(b"\r\n", b"\n")
    tree["usr/share/gtos/dunst.conf"] = FsNode("reg", 0o100644, dunst_cfg)
    tree["etc/dunst"] = FsNode("dir", 0o040755)
    tree["etc/dunst/dunstrc"] = FsNode("reg", 0o100644, dunst_cfg)
    tree["usr/share/gtos/update-channel.example"] = FsNode(
        "reg", 0o100644, "url=\n# example: url=https://example.com/gtos/\n".encode()
    )
    tree["usr/share/gtos/version"] = FsNode("reg", 0o100644, b"1.5.6\n")
    tree["boot"] = FsNode("dir", 0o040755) if "boot" not in tree else tree["boot"]
    tree["boot/gtos-version"] = FsNode("reg", 0o100644, b"1.5.6\n")
    # Тема рамок Openbox в стиле GT/OS (вместо Clearlooks)
    theme_src = ROOT / "assets" / "openbox" / "GTOS" / "openbox-3"
    if theme_src.is_dir():
        tree["usr/share/themes"] = FsNode("dir", 0o040755)
        tree["usr/share/themes/GTOS"] = FsNode("dir", 0o040755)
        tree["usr/share/themes/GTOS/openbox-3"] = FsNode("dir", 0o040755)
        for fp in theme_src.iterdir():
            if fp.is_file():
                tree[f"usr/share/themes/GTOS/openbox-3/{fp.name}"] = FsNode(
                    "reg", 0o100644, fp.read_bytes().replace(b"\r\n", b"\n")
                )
    # офлайн-копия каталога магазина (основной источник — сеть)
    for cand in (ROOT / "website" / "static" / "store" / "catalog.json", ROOT / "out" / "store-catalog.json"):
        if cand.is_file():
            tree["usr/share/gtos/store-catalog.json"] = FsNode("reg", 0o100644, cand.read_bytes())
            break

    # Свои иконки сторонних приложений (не GT DeskIconArt)
    def _resolve_bytes(path: str, depth: int = 0) -> bytes | None:
        if depth > 6 or path not in tree:
            return None
        node = tree[path]
        if node.kind == "lnk":
            target = node.data.decode("utf-8", "replace").lstrip("/")
            if not target.startswith("usr/") and "/" not in target:
                # relative link next to parent
                parent = "/".join(path.split("/")[:-1])
                target = f"{parent}/{target}".replace("//", "/")
            return _resolve_bytes(target, depth + 1)
        if node.kind == "reg" and node.data and len(node.data) > 200:
            return node.data
        return None

    icon_sources: dict[str, list[str]] = {
        "firefox": [
            "usr/lib/firefox/browser/chrome/icons/default/default256.png",
            "usr/lib/firefox/browser/chrome/icons/default/default128.png",
            "usr/share/icons/hicolor/384x384/apps/firefox.png",
            "usr/share/icons/hicolor/128x128/apps/firefox.png",
        ],
        "vlc": [
            "usr/share/icons/hicolor/256x256/apps/vlc.png",
            "usr/share/icons/hicolor/128x128/apps/vlc.png",
            "usr/share/icons/hicolor/48x48/apps/vlc.png",
            "usr/share/vlc/lua/http/images/vlc-48.png",
        ],
        "chromium": [
            "usr/share/icons/hicolor/256x256/apps/chromium.png",
            "usr/share/icons/hicolor/128x128/apps/chromium.png",
            "usr/share/icons/hicolor/48x48/apps/chromium.png",
        ],
        "telegram": [
            "usr/share/icons/hicolor/256x256/apps/telegram.png",
            "usr/share/icons/hicolor/128x128/apps/telegram-desktop.png",
            "usr/share/icons/hicolor/128x128/apps/telegram.png",
            "usr/share/icons/hicolor/48x48/apps/telegram.png",
        ],
        "gimp": [
            "usr/share/icons/hicolor/256x256/apps/gimp.png",
            "usr/share/icons/hicolor/128x128/apps/gimp.png",
            "usr/share/icons/hicolor/48x48/apps/gimp.png",
        ],
        "libreoffice": [
            "usr/share/icons/hicolor/256x256/apps/libreoffice-main.png",
            "usr/share/icons/hicolor/128x128/apps/libreoffice-writer.png",
            "usr/share/icons/hicolor/128x128/apps/libreoffice-main.png",
            "usr/share/icons/hicolor/48x48/apps/libreoffice-main.png",
        ],
    }
    tree["usr/share/gtos/app-icons"] = FsNode("dir", 0o040755)
    packed = 0
    for app_id, cands in icon_sources.items():
        data = None
        for cand in cands:
            data = _resolve_bytes(cand)
            if data:
                break
        if data:
            tree[f"usr/share/gtos/app-icons/{app_id}.png"] = FsNode("reg", 0o100644, data)
            packed += 1
    print(f"app-icons packed: {packed}")

    write_cpio(tree, INITRD)
    print(f"updated {INITRD} ({INITRD.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
