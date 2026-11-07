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

Current stable release: **1.5.6**.

| | |
|---|---|
| **Architecture** | x86_64 |
| **Base** | Linux (Alpine packages) + custom initrd |
| **Shell** | Qt 6 / QML |
| **Boot** | BIOS / Legacy ISO (UEFI via Ventoy) |
| **Author** | Glukhov Mikhail |

## Features

- **Desktop shell** — Start, dock, virtual desktops, notifications, Alt+Tab, Win+V clipboard
- **Apps** — Files, Browser, Terminal, Gallery, Weather, Media Player, Store (Alpine / Linux / Windows via Wine)
- **System** — Settings, Control Center, Diagnostics, Update Engine, Security, Recovery & backups
- **Secure desk** — Ctrl+Alt+Delete overlay (lock, switch user, sign out, Task Manager, power)
- **Safe Mode** — minimal services for recovery (`gtos.safemode=1`)
- **Persistence** — install to disk with GRUB, or run live with a data volume

## Download

Official images are published as GitHub Releases:

**[→ GT/OS 1.5.6 (latest)](https://github.com/vi1wer/gtos/releases/latest)**

| Release | File |
|---------|------|
| 1.5.6 (current) | [`GTOS-1.5.6-x86_64.iso`](https://github.com/vi1wer/gtos/releases/tag/v1.5.6) |
| Archive | [All releases](https://github.com/vi1wer/gtos/releases) |

Checksums: prefer verifying the asset size on the release page after download.

## Install

1. Download the ISO for your version.
2. Write it to a USB stick (Rufus, balenaEtcher, or Ventoy).
3. Boot from USB (Legacy BIOS; for UEFI use Ventoy).
4. In the live session open **Start → Install GT/OS** to install to disk and set up GRUB.

### Boot menu

At the ISO boot prompt (`Tab` to list labels):

| Label | Mode |
|-------|------|
| `gtos` | Normal |
| `safemode` | Safe Mode |
| `verbose` | Verbose logging |

After disk install, GRUB offers the same Normal / Safe Mode / Verbose entries.

## Safe Mode

Use when the desktop misbehaves or you need a quieter boot:

- ISO / GRUB → **GT/OS (Safe Mode)**
- In session → **Ctrl+Alt+Delete → Safe Mode** (reboot with minimal services)
- QEMU → `python run.py --safe`

In Safe Mode automatic Wi‑Fi reconnect and CUPS are skipped; the Store catalog is not fetched in the background.

## System requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 64-bit x86 | dual-core+ |
| RAM | 4 GB | 8 GB+ |
| Disk (install) | 16 GB | 32 GB+ |
| Display | 1280×720 | 1920×1080 |

## Build from source

```bash
# Full image (kernel + initrd)
python build.py
python make_iso.py --version 1.5.6

# Run in QEMU
python run.py
python run.py --safe

# After QML / assets changes (fast path)
python refresh_ui.py
python run.py
```

Local product site (changelog, blog, downloads):

```bash
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
make_iso.py   BIOS-bootable ISO
run.py        QEMU launcher
```

## Status

GT/OS is an actively developed desktop OS product. Releases are versioned ISO images; the shell and site ship together with each cut.

## License

Copyright © 2026 Glukhov Mikhail. All rights reserved.  
See [LICENSE](LICENSE).

---

<p align="center">GT/OS · Glukhov Mikhail</p>
