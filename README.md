<p align="center">
  <img src="website/static/img/gt-mark.svg" alt="GT/OS" width="72" height="72">
</p>

<h1 align="center">GT/OS</h1>

<p align="center">
  <strong>Desktop operating system</strong> by Glukhov Mikhail<br>
  Linux kernel · Alpine userland · Qt 6 shell
</p>

<p align="center">
  <a href="https://github.com/vi1wer/gtos/releases/latest"><img src="https://img.shields.io/github/v/release/vi1wer/gtos?label=latest&color=3be182" alt="Latest release"></a>
  <a href="https://github.com/vi1wer/gtos/releases"><img src="https://img.shields.io/github/downloads/vi1wer/gtos/total?color=1a2a24" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/boot-BIOS%20%2B%20UEFI-143028" alt="BIOS+UEFI">
  <img src="https://img.shields.io/badge/platform-x86__64-0e1816" alt="x86_64">
  <img src="https://img.shields.io/badge/UI-Qt%206%20%2F%20QML-143028" alt="Qt 6">
</p>

<p align="center">
  <a href="https://github.com/vi1wer/gtos/releases/latest"><strong>Download ISO</strong></a>
  ·
  <a href="#features">Features</a>
  ·
  <a href="#install">Install</a>
  ·
  <a href="#build-from-source">Build</a>
</p>

---

## What is GT/OS?

GT/OS is a full desktop operating system: its own Start menu, dock, Settings, Control Center, Store, Files, and system services — not a theme on someone else’s desktop.

Current stable release: **1.6**.

| | |
|---|---|
| **Architecture** | x86_64 |
| **Base** | Linux (Alpine packages) + custom initrd |
| **Shell** | Qt 6 / QML |
| **Boot** | BIOS + UEFI (El Torito) |
| **Author** | Glukhov Mikhail |

## Features

- **Desktop shell** — Start, dock, virtual desktops, notifications, Alt+Tab, Win+V clipboard
- **Apps** — Files, Browser, Terminal, Gallery, Weather, Media Player, Store
- **System** — Settings, Control Center, Diagnostics, Update Engine, Security, Recovery & backups
- **UEFI + BIOS** — official ISO boots on modern firmware without Ventoy
- **HiDPI** — UI scale 100% / 125% / 150% / 200%
- **Onboarding** — account → language → network → backup tips
- **Updates** — check → install → install & reboot
- **Secure desk** — Ctrl+Alt+Delete overlay
- **Safe Mode** — minimal services (`gtos.safemode=1`)
- **Sleep / resume** — network and audio restored after wake
- **Verified images** — `.sha256` next to every ISO

## Download

**[→ GT/OS 1.6 (latest)](https://github.com/vi1wer/gtos/releases/latest)**

Verify after download:

```bash
sha256sum -c GTOS-1.6-x86_64.iso.sha256
```

| Release | File |
|---------|------|
| 1.6 (current) | [`GTOS-1.6-x86_64.iso`](https://github.com/vi1wer/gtos/releases/tag/v1.6) |
| Archive | [All releases](https://github.com/vi1wer/gtos/releases) |

## Install

1. Download the ISO and its `.sha256`.
2. Write the ISO to USB (Rufus, balenaEtcher, or Ventoy).
3. Boot from USB (**UEFI or Legacy**).
4. In the live session: **Start → Install GT/OS**.

### Boot menu

| Entry | Mode |
|-------|------|
| GT/OS | Normal |
| Safe Mode | Minimal services |
| verbose | Verbose logging |

## Safe Mode

- ISO / GRUB → **Safe Mode**
- Session → **Ctrl+Alt+Delete → Safe Mode**
- QEMU → `python run.py --safe`

## System requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 64-bit x86 | dual-core+ |
| RAM | 4 GB | 8 GB+ |
| Disk (install) | 16 GB | 32 GB+ |
| Display | 1280×720 | 1920×1080 |
| Firmware | BIOS or UEFI | UEFI |

## Build from source

```bash
python build.py
python make_iso.py --version 1.6
python run.py
python run.py --safe

# After QML / assets changes
python refresh_ui.py
python run.py

# Local site
python website/app.py   # http://127.0.0.1:5050
```

### Repository layout

```
qml/          Desktop shell (Main.qml)
src/          gt-shell (C++ / Qt bridge)
scripts/      Installer, store, session helpers
website/      Product site
assets/       Wallpapers, fonts, Openbox theme
build.py      Rootfs / initrd builder
make_iso.py   BIOS + UEFI ISO (+ SHA256)
run.py        QEMU launcher
```

## License

Copyright © 2026 Glukhov Mikhail. All rights reserved.  
See [LICENSE](LICENSE).

---

<p align="center">GT/OS · Glukhov Mikhail</p>
