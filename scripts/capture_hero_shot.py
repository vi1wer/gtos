#!/usr/bin/env python3
"""Boot GT/OS in QEMU briefly and capture a native 1920×1080 screendump for the site hero."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageFilter, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KERNEL = OUT / "vmlinuz"
INITRD = OUT / "gtos-rootfs.cpio.gz"
DATA = OUT / "gtos-data.qcow2"
QEMU = Path(r"D:\DeepOS\tools\qemu\qemu-system-x86_64.exe")
DEST = ROOT / "website" / "static" / "img" / "gtos-desktop-shot.png"
PPM = OUT / "hero-screendump.ppm"
QMP_PORT = 4445


def find_bios(qemu: Path) -> Path:
    for cand in (qemu.parent / "share" / "qemu", qemu.parent):
        if (cand / "bios.bin").is_file() or (cand / "bios-256k.bin").is_file():
            return cand
    return qemu.parent


def qmp_recv(sock: socket.socket) -> dict:
    buf = b""
    while True:
        chunk = sock.recv(8192)
        if not chunk:
            raise RuntimeError("QMP closed")
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                return json.loads(line.decode("utf-8"))


def qmp_exec(sock: socket.socket, cmd: dict) -> dict:
    sock.sendall((json.dumps(cmd) + "\n").encode("utf-8"))
    return qmp_recv(sock)


def wait_qmp(timeout: float = 60.0) -> socket.socket:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", QMP_PORT), timeout=1.0)
            return sock
        except OSError:
            time.sleep(0.4)
    raise RuntimeError("QMP did not come up")


def process_ppm(ppm: Path, dest: Path) -> None:
    im = Image.open(ppm).convert("RGB")
    w, h = im.size
    print(f"raw screendump {w}x{h}")

    # trim near-black letterbox if any
    arr_corner = im.crop((0, 0, 8, 8))
    # keep full frame — guest is already the desktop
    # light sharpen for UI chrome after any resize
    if w < 1600:
        im = im.resize((1920, int(1920 * h / w)), Image.Resampling.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
    else:
        # mild clarity only
        im = ImageEnhance.Sharpness(im).enhance(1.15)
        im = ImageEnhance.Contrast(im).enhance(1.04)

    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG", optimize=True, compress_level=6)
    # also a high-quality JPEG fallback for browsers that prefer it
    jpg = dest.with_suffix(".jpg")
    im.save(jpg, format="JPEG", quality=92, optimize=True, progressive=True)
    print(f"saved {dest} ({dest.stat().st_size} bytes) and {jpg.name}")


def main() -> int:
    if not KERNEL.is_file() or not INITRD.is_file():
        print("missing kernel/initrd")
        return 1
    if not QEMU.is_file():
        print("qemu not found")
        return 1

    # stop any existing qemu
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='qemu-system-x86_64.exe'\" "
         "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        check=False,
    )
    time.sleep(1)

    bios = find_bios(QEMU)
    smp = str(min(8, max(4, (os.cpu_count() or 4) // 2)))
    args = [
        str(QEMU), "-L", str(bios),
        "-accel", "tcg,thread=multi,tb-size=256",
        "-cpu", "qemu64",
        "-m", "14336",
        "-smp", smp,
        "-kernel", str(KERNEL),
        "-initrd", str(INITRD),
        "-append",
        "console=tty0 console=ttyS0,115200 rdinit=/init quiet loglevel=2 video=1920x1080 noapic",
        "-device", "virtio-vga,xres=1920,yres=1080",
        "-display",
        "gtk,gl=off,full-screen=off,grab-on-hover=off,zoom-to-fit=on,show-cursor=on,window-close=on",
        "-usb", "-device", "usb-tablet",
        "-name", "GT/OS 1.6 shot",
        "-netdev", "user,id=net0",
        "-device", "virtio-net-pci,netdev=net0,romfile=",
        "-qmp", f"tcp:127.0.0.1:{QMP_PORT},server,nowait",
        "-no-reboot",
    ]
    if DATA.is_file():
        args += ["-drive", f"file={DATA},if=virtio,format=qcow2,cache=writeback"]

    print("starting QEMU…", flush=True)
    proc = subprocess.Popen(args)
    try:
        sock = wait_qmp()
        banner = qmp_recv(sock)
        print("QMP", banner.get("QMP", {}).get("version", {}).get("qemu", {}), flush=True)
        print("caps", qmp_exec(sock, {"execute": "qmp_capabilities"}), flush=True)

        # wait for shell/desktop (TCG boot is slow)
        wait_s = 70
        print(f"waiting {wait_s}s for desktop…", flush=True)
        time.sleep(wait_s)

        if PPM.exists():
            PPM.unlink()
        # QEMU on Windows prefers forward slashes
        fname = str(PPM).replace("\\", "/")
        res = qmp_exec(sock, {"execute": "screendump", "arguments": {"filename": fname}})
        print("screendump", res, flush=True)
        time.sleep(1.5)
        if not PPM.is_file() or PPM.stat().st_size < 1000:
            raise RuntimeError("screendump file missing/empty")
        process_ppm(PPM, DEST)
        sock.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
