#!/usr/bin/env python3
"""Полный цикл после правок: initrd → ISO → сайт → QEMU.

Использование:
  python ship.py              # UI + ISO 1.5 + сайт + запуск ОС
  python ship.py --no-qemu    # только сборка и сайт
  python ship.py --version 1.5
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], *, check: bool = True) -> int:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r.returncode


def stop_qemu() -> None:
    if os.name != "nt":
        subprocess.run(["pkill", "-f", "qemu-system-x86_64"], check=False)
        return
    for name in ("qemu-system-x86_64.exe", "qemu-system-x86_64w.exe"):
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    # дождёмся отпускания initrd
    time.sleep(1.5)


def restart_website() -> None:
    if os.name == "nt":
        # убить процесс на 5050
        ps = (
            "$ids = Get-NetTCPConnection -LocalPort 5050 -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty OwningProcess -Unique; "
            "foreach ($i in $ids) { if ($i) { Stop-Process -Id $i -Force -ErrorAction SilentlyContinue } }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.8)
        subprocess.Popen(
            [sys.executable, str(ROOT / "website" / "app.py")],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        subprocess.Popen(
            [sys.executable, str(ROOT / "website" / "app.py")],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    time.sleep(1.2)
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:5050/", timeout=3) as resp:
            print(f"сайт :5050 → {resp.status}", flush=True)
    except Exception as exc:
        print(f"сайт :5050 пока не ответил ({exc})", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка + выкладка + запуск GT/OS")
    ap.add_argument("--version", default="1.5", help="версия ISO (по умолчанию 1.5)")
    ap.add_argument("--no-qemu", action="store_true", help="не запускать QEMU")
    ap.add_argument("--no-site", action="store_true", help="не перезапускать сайт")
    ap.add_argument("--skip-iso", action="store_true", help="только refresh_ui (без make_iso)")
    args = ap.parse_args()

    print("=== ship: останавливаю QEMU (чтобы отпустить initrd) ===", flush=True)
    stop_qemu()

    print("=== ship: refresh_ui ===", flush=True)
    run([sys.executable, "refresh_ui.py"])

    if not args.skip_iso:
        print(f"=== ship: make_iso {args.version} ===", flush=True)
        run([sys.executable, "make_iso.py", "--version", args.version])

    if not args.no_site:
        print("=== ship: сайт ===", flush=True)
        restart_website()

    if args.no_qemu:
        print("Готово (без QEMU).", flush=True)
        return 0

    print("=== ship: QEMU ===", flush=True)
    # run.py блокирует до закрытия окна — это нормально
    return run([sys.executable, "run.py"], check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
