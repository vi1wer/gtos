#!/usr/bin/env python3
"""Boot GT/OS as a daily desktop: disk persistence + user networking."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Windows cp1251 ломает print с ×/— и валит запуск до QEMU
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
KERNEL = OUT / "vmlinuz"
INITRD = OUT / "gtos-rootfs.cpio.gz"
DATA_IMG = OUT / "gtos-data.qcow2"
USERDATA = OUT / "userdata"


def find_qemu() -> Path | None:
    candidates = [
        Path(r"D:\DeepOS\tools\qemu\qemu-system-x86_64.exe"),
        Path(r"D:\OS\MillenniumOS\tools\qemu\qemu-system-x86_64.exe"),
        ROOT / "tools" / "qemu" / "qemu-system-x86_64.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def find_qemu_img(qemu: Path) -> Path | None:
    for path in (qemu.parent / "qemu-img.exe", qemu.parent / "qemu-img"):
        if path.is_file():
            return path
    return None


def bios_dir(qemu: Path) -> Path | None:
    for candidate in (qemu.parent / "share", qemu.parent.parent / "share" / "qemu"):
        if (candidate / "bios-256k.bin").is_file():
            return candidate.resolve()
    return None


def ensure_persist(qemu: Path) -> None:
    USERDATA.mkdir(parents=True, exist_ok=True)
    (USERDATA / "home").mkdir(exist_ok=True)
    (USERDATA / "gtos").mkdir(exist_ok=True)
    img = find_qemu_img(qemu)
    if img is None:
        if not DATA_IMG.is_file():
            print("qemu-img не найден — постоянный диск не создан.")
        return
    # Минимум как у установки на ПК: от 16 ГБ
    target = "16G"
    target_bytes = 16 * 1024 * 1024 * 1024
    if not DATA_IMG.is_file():
        print(f"Создаю постоянный диск {DATA_IMG.name} ({target})…")
        subprocess.run(
            [str(img), "create", "-f", "qcow2", str(DATA_IMG), target],
            check=True,
        )
        return
    # Уже есть — расширяем до 16 ГБ без потери данных (ФС дорастёт при загрузке)
    try:
        info = subprocess.run(
            [str(img), "info", "--output=json", str(DATA_IMG)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        virtual = int(json.loads(info).get("virtual-size") or 0)
        if virtual < target_bytes:
            print(f"Расширяю {DATA_IMG.name} до {target}…")
            subprocess.run([str(img), "resize", str(DATA_IMG), target], check=True)
    except Exception as exc:
        print(f"Не удалось проверить/расширить диск: {exc}")


def qemu_supports_accel(qemu: Path, name: str) -> bool:
    try:
        out = subprocess.run(
            [str(qemu), "-accel", "help"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        blob = (out.stdout or "") + (out.stderr or "")
        return name.lower() in blob.lower()
    except Exception:
        return False


def pick_accel(qemu: Path) -> tuple[list[str], str]:
    """По умолчанию TCG. WHPX — только с --whpx (нужна платформа гипервизора Windows)."""
    if "--whpx" in sys.argv and qemu_supports_accel(qemu, "whpx"):
        return ["-accel", "whpx,kernel-irqchip=off", "-cpu", "max,hv_relaxed,hv_vapic,hv_time"], "WHPX"
    return ["-accel", "tcg,thread=multi,tb-size=256"], "TCG"


def pick_display_gpu() -> tuple[list[str], str, bool]:
    """VirGL (virtio-vga-gl + gtk,gl=on). Флаг: --no-gl — software как раньше."""
    if "--no-gl" in sys.argv or "--safe" in sys.argv:
        return (
            [
                "-device",
                "virtio-vga,xres=1920,yres=1080",
                "-display",
                "gtk,gl=off,full-screen=off,grab-on-hover=off,zoom-to-fit=on,show-cursor=on,window-close=on",
            ],
            "GTK·soft",
            False,
        )
    return (
        [
            "-device",
            "virtio-vga-gl,xres=1920,yres=1080",
            "-display",
            "gtk,gl=on,full-screen=off,grab-on-hover=off,zoom-to-fit=on,show-cursor=on,window-close=on",
        ],
        "VirGL",
        True,
    )


def main() -> int:
    if not KERNEL.is_file() or not INITRD.is_file():
        print("Образ ещё не собран. Запусти: python build.py")
        return 1
    qemu = find_qemu()
    if qemu is None:
        print("qemu-system-x86_64.exe не найден.")
        return 1
    safe = "--safe" in sys.argv
    ensure_persist(qemu)
    serial_log = OUT / "gui-serial.log"
    smp = str(min(8, max(4, (os.cpu_count() or 4) // 2)))
    accel_args, accel_label = pick_accel(qemu)
    gpu_args, gpu_label, virgl = pick_display_gpu()

    append = "console=tty0 console=ttyS0,115200 rdinit=/init quiet loglevel=2 video=1920x1080"
    # noapic оставляем только для TCG (на WHPX мешает)
    if accel_label == "TCG":
        append += " noapic"
    if safe:
        append += " gtos.safemode=1"
    if virgl:
        append += " gtos.gpu=virgl"

    args: list[str] = [
        *accel_args,
    ]
    # pick_accel уже мог добавить -cpu для WHPX; для TCG — qemu64
    if "-cpu" not in args:
        args += ["-cpu", "qemu64"]
    args += [
        "-m",
        "14336",
        "-smp",
        smp,
        "-kernel",
        str(KERNEL),
        "-initrd",
        str(INITRD),
        "-append",
        append,
        *gpu_args,
        "-usb",
        "-device",
        "usb-tablet",
        "-name",
        "GT/OS 1.6.2" + (" Safe" if safe else ""),
        "-serial",
        f"file:{serial_log}",
        "-netdev",
        "user,id=net0,hostfwd=tcp::2222-:22",
        # romfile= — без PXE option ROM, иначе SeaBIOS зависает на "Booting from ROM"
        "-device",
        "virtio-net-pci,netdev=net0,romfile=",
    ]
    if DATA_IMG.is_file():
        # writethrough: настройки не теряются при kill окна QEMU (writeback откладывал fsync)
        args += ["-drive", f"file={DATA_IMG},if=virtio,format=qcow2,cache=writethrough"]
    # ISO не монтируем в run.py: загрузка идёт через -kernel/-initrd
    args.append("-no-reboot")
    bios = bios_dir(qemu)
    if bios is not None:
        args = ["-L", str(bios), *args]
    print(f"QEMU: {qemu}", flush=True)
    mode = "Safe Mode · " if safe else ""
    print(
        f"GT/OS 1.6.2 — {mode}1920×1080 · 14 ГБ ОЗУ · диск 16 ГБ · {accel_label} · {gpu_label}",
        flush=True,
    )
    if virgl:
        print("GPU: VirGL (хост OpenGL). Откат: python run.py --no-gl", flush=True)
    print("Закрой окно QEMU, чтобы выключить систему.", flush=True)
    try:
        return subprocess.run([str(qemu), *args], check=False).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
