#!/usr/bin/env python3
"""Generate GT Store catalog: popular apps people actually want (not Alpine junk)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import build

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "website" / "static" / "store" / "catalog.json"
OUT_SHARE = ROOT / "out" / "store-catalog.json"

# Ручной каталог: узнаваемые приложения. apk — имя пакета Alpine, если есть.
# source web — без apk, открывается по URL.
CURATED: list[dict] = [
    # Интернет
    {"id": "firefox", "apk": "firefox", "name": "Firefox", "pub": "Mozilla", "cat": "Интернет",
     "desc": "Быстрый браузер с защитой приватности", "iconKind": "browser",
     "homeUrl": "https://www.mozilla.org/firefox/", "featured": True},
    {"id": "chromium", "apk": "chromium", "name": "Google Chrome / Chromium", "pub": "The Chromium Authors", "cat": "Интернет",
     "desc": "Браузер на движке Chrome для повседневного веба", "iconKind": "browser",
     "homeUrl": "https://www.google.com/chrome/", "featured": True},
    {"id": "thunderbird", "apk": "thunderbird", "name": "Thunderbird", "pub": "Mozilla", "cat": "Интернет",
     "desc": "Почта, календарь и фильтры писем", "iconKind": "mail", "featured": True},
    {"id": "telegram", "apk": "telegram-desktop", "name": "Telegram", "pub": "Telegram FZ-LLC", "cat": "Интернет",
     "desc": "Мессенджер с облачными чатами и файлами", "iconKind": "browser",
     "homeUrl": "https://web.telegram.org/k/", "featured": True, "launchId": "telegram"},
    {"id": "discord", "apk": "", "name": "Discord", "pub": "Discord Inc.", "cat": "Интернет",
     "desc": "Голос, чаты и сообщества", "iconKind": "browser",
     "homeUrl": "https://discord.com/app", "source": "web", "launchId": "browser"},
    {"id": "whatsapp", "apk": "", "name": "WhatsApp", "pub": "Meta", "cat": "Интернет",
     "desc": "Мессенджер WhatsApp Web", "iconKind": "browser",
     "homeUrl": "https://web.whatsapp.com/", "source": "web", "launchId": "browser"},
    {"id": "element", "apk": "element-desktop", "name": "Element", "pub": "New Vector", "cat": "Интернет",
     "desc": "Клиент Matrix для защищённых чатов", "iconKind": "browser"},
    {"id": "filezilla", "apk": "filezilla", "name": "FileZilla", "pub": "FileZilla Project", "cat": "Интернет",
     "desc": "FTP и SFTP для передачи файлов", "iconKind": "files"},
    {"id": "qbittorrent", "apk": "qbittorrent", "name": "qBittorrent", "pub": "The qBittorrent project", "cat": "Интернет",
     "desc": "Торрент-клиент без рекламы", "iconKind": "files"},
    {"id": "transmission", "apk": "transmission", "name": "Transmission", "pub": "Transmission Project", "cat": "Интернет",
     "desc": "Лёгкий торрент-клиент", "iconKind": "files"},
    # Офис
    {"id": "libreoffice", "apk": "libreoffice", "name": "LibreOffice", "pub": "The Document Foundation", "cat": "Офис",
     "desc": "Документы, таблицы и презентации", "iconKind": "notes", "featured": True, "launchId": "notes"},
    {"id": "onlyoffice", "apk": "", "name": "ONLYOFFICE", "pub": "Ascensio System", "cat": "Офис",
     "desc": "Редактор документов в браузере", "iconKind": "notes",
     "homeUrl": "https://www.onlyoffice.com/", "source": "web", "launchId": "browser"},
    {"id": "obsidian", "apk": "", "name": "Obsidian", "pub": "Obsidian.md", "cat": "Офис",
     "desc": "База знаний на Markdown", "iconKind": "notes",
     "homeUrl": "https://obsidian.md/", "source": "web", "launchId": "browser"},
    {"id": "abiword", "apk": "abiword", "name": "AbiWord", "pub": "AbiSource", "cat": "Офис",
     "desc": "Лёгкий текстовый процессор", "iconKind": "notes", "launchId": "notes"},
    {"id": "gnumeric", "apk": "gnumeric", "name": "Gnumeric", "pub": "GNOME", "cat": "Офис",
     "desc": "Электронные таблицы", "iconKind": "notes", "launchId": "notes"},
    {"id": "evince", "apk": "evince", "name": "Evince", "pub": "GNOME", "cat": "Офис",
     "desc": "Просмотр PDF и документов", "iconKind": "notes"},
    {"id": "okular", "apk": "okular", "name": "Okular", "pub": "KDE", "cat": "Офис",
     "desc": "Универсальный просмотрщик документов", "iconKind": "notes"},
    # Медиа
    {"id": "vlc", "apk": "vlc", "name": "VLC media player", "pub": "VideoLAN", "cat": "Медиа",
     "desc": "Воспроизведение почти любого видео и аудио", "iconKind": "video",
     "featured": True, "launchId": "vlc", "engineBins": ["vlc", "cvlc"]},
    {"id": "mpv", "apk": "mpv", "name": "mpv", "pub": "mpv.io", "cat": "Медиа",
     "desc": "Минималистичный видеоплеер", "iconKind": "video", "launchId": "pkg"},
    {"id": "audacious", "apk": "audacious", "name": "Audacious", "pub": "Audacious Team", "cat": "Медиа",
     "desc": "Лёгкий аудиоплеер", "iconKind": "music", "launchId": "music"},
    {"id": "rhythmbox", "apk": "rhythmbox", "name": "Rhythmbox", "pub": "GNOME", "cat": "Медиа",
     "desc": "Музыкальная библиотека", "iconKind": "music", "launchId": "music"},
    {"id": "spotify", "apk": "", "name": "Spotify", "pub": "Spotify AB", "cat": "Медиа",
     "desc": "Музыкальный стриминг в браузере", "iconKind": "music",
     "homeUrl": "https://open.spotify.com/", "source": "web", "launchId": "browser"},
    {"id": "youtube", "apk": "", "name": "YouTube", "pub": "Google", "cat": "Медиа",
     "desc": "Видео и музыка YouTube", "iconKind": "video",
     "homeUrl": "https://www.youtube.com/", "source": "web", "launchId": "browser"},
    {"id": "obs", "apk": "obs-studio", "name": "OBS Studio", "pub": "OBS Project", "cat": "Медиа",
     "desc": "Запись экрана и стримы", "iconKind": "video"},
    # Творчество
    {"id": "gimp", "apk": "gimp", "name": "GIMP", "pub": "GIMP Team", "cat": "Творчество",
     "desc": "Редактор растровой графики", "iconKind": "draw", "featured": True, "launchId": "draw"},
    {"id": "inkscape", "apk": "inkscape", "name": "Inkscape", "pub": "Inkscape Project", "cat": "Творчество",
     "desc": "Векторный редактор SVG", "iconKind": "draw", "featured": True, "launchId": "draw"},
    {"id": "blender", "apk": "blender", "name": "Blender", "pub": "Blender Foundation", "cat": "Творчество",
     "desc": "3D-моделирование и анимация", "iconKind": "draw", "featured": True, "launchId": "draw"},
    {"id": "krita", "apk": "krita", "name": "Krita", "pub": "Krita Foundation", "cat": "Творчество",
     "desc": "Рисование и цифровая живопись", "iconKind": "draw", "launchId": "draw"},
    {"id": "darktable", "apk": "darktable", "name": "darktable", "pub": "darktable team", "cat": "Творчество",
     "desc": "Обработка фотографий", "iconKind": "draw"},
    {"id": "shotcut", "apk": "shotcut", "name": "Shotcut", "pub": "Meltytech", "cat": "Творчество",
     "desc": "Видеомонтаж", "iconKind": "video"},
    {"id": "audacity", "apk": "audacity", "name": "Audacity", "pub": "Audacity Team", "cat": "Творчество",
     "desc": "Редактор звука", "iconKind": "music"},
    {"id": "figma", "apk": "", "name": "Figma", "pub": "Figma Inc.", "cat": "Творчество",
     "desc": "Дизайн интерфейсов в браузере", "iconKind": "draw",
     "homeUrl": "https://www.figma.com/", "source": "web", "launchId": "browser"},
    # Разработка
    {"id": "vscode", "apk": "code-oss", "name": "Visual Studio Code", "pub": "Microsoft / OSS", "cat": "Разработка",
     "desc": "Редактор кода с расширениями", "iconKind": "term", "featured": True, "launchId": "pkg"},
    {"id": "neovim", "apk": "neovim", "name": "Neovim", "pub": "Neovim Team", "cat": "Разработка",
     "desc": "Современный Vim", "iconKind": "term", "launchId": "pkg"},
    {"id": "vim", "apk": "vim", "name": "Vim", "pub": "Bram Moolenaar", "cat": "Разработка",
     "desc": "Классический редактор кода", "iconKind": "term", "launchId": "pkg"},
    {"id": "git", "apk": "git", "name": "Git", "pub": "Git SCM", "cat": "Разработка",
     "desc": "Система контроля версий", "iconKind": "term", "launchId": "pkg"},
    {"id": "gitcola", "apk": "git-cola", "name": "Git Cola", "pub": "git-cola", "cat": "Разработка",
     "desc": "Графический клиент Git", "iconKind": "term", "launchId": "pkg"},
    {"id": "python3", "apk": "python3", "name": "Python 3", "pub": "Python Software Foundation", "cat": "Разработка",
     "desc": "Язык программирования Python", "iconKind": "term", "launchId": "pkg"},
    {"id": "nodejs", "apk": "nodejs", "name": "Node.js", "pub": "OpenJS Foundation", "cat": "Разработка",
     "desc": "JavaScript на сервере", "iconKind": "term", "launchId": "pkg"},
    {"id": "docker", "apk": "docker", "name": "Docker", "pub": "Docker Inc.", "cat": "Разработка",
     "desc": "Контейнеры для приложений", "iconKind": "term", "launchId": "pkg"},
    {"id": "github", "apk": "", "name": "GitHub", "pub": "GitHub", "cat": "Разработка",
     "desc": "Репозитории и CI в браузере", "iconKind": "browser",
     "homeUrl": "https://github.com/", "source": "web", "launchId": "browser"},
    # Утилиты
    {"id": "keepassxc", "apk": "keepassxc", "name": "KeePassXC", "pub": "KeePassXC Team", "cat": "Утилиты",
     "desc": "Менеджер паролей с локальной базой", "iconKind": "settings"},
    {"id": "bitwarden", "apk": "", "name": "Bitwarden", "pub": "Bitwarden Inc.", "cat": "Утилиты",
     "desc": "Менеджер паролей в браузере", "iconKind": "settings",
     "homeUrl": "https://vault.bitwarden.com/", "source": "web", "launchId": "browser"},
    {"id": "7zip", "apk": "7zip", "name": "7-Zip", "pub": "Igor Pavlov", "cat": "Утилиты",
     "desc": "Архиватор 7z / zip / rar", "iconKind": "files", "launchId": "pkg"},
    {"id": "htop", "apk": "htop", "name": "htop", "pub": "Hisham Muhammad", "cat": "Утилиты",
     "desc": "Монитор процессов", "iconKind": "monitor", "featured": True, "launchId": "pkg"},
    {"id": "gparted", "apk": "gparted", "name": "GParted", "pub": "GParted Team", "cat": "Утилиты",
     "desc": "Управление разделами диска", "iconKind": "files"},
    {"id": "timeshift", "apk": "timeshift", "name": "Timeshift", "pub": "TeejeeTech", "cat": "Утилиты",
     "desc": "Снимки системы и откат", "iconKind": "settings"},
    {"id": "flameshot", "apk": "flameshot", "name": "Flameshot", "pub": "Flameshot", "cat": "Утилиты",
     "desc": "Снимки экрана с разметкой", "iconKind": "draw"},
    {"id": "calculator", "apk": "galculator", "name": "Калькулятор", "pub": "galculator", "cat": "Утилиты",
     "desc": "Простой калькулятор", "iconKind": "calc", "launchId": "calc"},
    # Система
    {"id": "gnome-system-monitor", "apk": "gnome-system-monitor", "name": "Системный монитор", "pub": "GNOME", "cat": "Система",
     "desc": "ЦП, память и процессы", "iconKind": "monitor", "launchId": "monitor"},
    {"id": "baobab", "apk": "baobab", "name": "Анализатор диска", "pub": "GNOME", "cat": "Система",
     "desc": "Что занимает место на диске", "iconKind": "files"},
    {"id": "gnome-disk-utility", "apk": "gnome-disk-utility", "name": "Диски", "pub": "GNOME", "cat": "Система",
     "desc": "Управление дисками и образами", "iconKind": "files"},
    {"id": "wireguard", "apk": "wireguard-tools", "name": "WireGuard", "pub": "Jason A. Donenfeld", "cat": "Система",
     "desc": "VPN WireGuard", "iconKind": "settings", "launchId": "pkg"},

    # —— Linux (не Alpine): AppImage / .deb ——
    {"id": "cursor-linux", "apk": "", "name": "Cursor", "pub": "Anysphere", "cat": "Разработка",
     "desc": "AI-IDE на базе VS Code — скачивается по умолчанию при первом входе", "iconKind": "term",
     "source": "linux", "platform": "linux", "format": "appimage", "featured": True, "launchId": "pkg",
     "url": "https://downloads.cursor.com/production/306d153d51d714882ab7b1bc49649cab624e8a31/linux/x64/Cursor-3.29.9-x86_64.AppImage",
     "bin": "cursor", "version": "3.29.9", "size": 0, "available": True, "defaultDownload": True},
    {"id": "obsidian-linux", "apk": "", "name": "Obsidian", "pub": "Obsidian.md", "cat": "Офис",
     "desc": "База знаний Markdown — Linux AppImage (не Alpine)", "iconKind": "notes",
     "source": "linux", "platform": "linux", "format": "appimage", "featured": True, "launchId": "pkg",
     "url": "https://github.com/obsidianmd/obsidian-releases/releases/download/v1.8.4/Obsidian-1.8.4.AppImage",
     "version": "1.8.4", "size": 0, "available": True},
    {"id": "vscodium-linux", "apk": "", "name": "VSCodium", "pub": "VSCodium", "cat": "Разработка",
     "desc": "VS Code без телеметрии Microsoft — Linux AppImage", "iconKind": "term",
     "source": "linux", "platform": "linux", "format": "appimage", "featured": True, "launchId": "pkg",
     "url": "https://github.com/VSCodium/vscodium/releases/download/1.96.4.25017/VSCodium-1.96.4.25017-x86_64.AppImage",
     "bin": "codium", "version": "1.96.4", "size": 0, "available": True},
    {"id": "bitwarden-linux", "apk": "", "name": "Bitwarden Desktop", "pub": "Bitwarden Inc.", "cat": "Утилиты",
     "desc": "Менеджер паролей — Linux AppImage", "iconKind": "settings",
     "source": "linux", "platform": "linux", "format": "appimage", "launchId": "pkg",
     "url": "https://github.com/bitwarden/clients/releases/download/desktop-v2025.1.3/Bitwarden-2025.1.3-x86_64.AppImage",
     "version": "2025.1.3", "size": 0, "available": True},
    {"id": "joplin-linux", "apk": "", "name": "Joplin", "pub": "Laurent Cozic", "cat": "Офис",
     "desc": "Заметки с синхронизацией — Linux AppImage", "iconKind": "notes",
     "source": "linux", "platform": "linux", "format": "appimage", "launchId": "pkg",
     "url": "https://github.com/laurent22/joplin/releases/download/v3.2.13/Joplin-3.2.13.AppImage",
     "version": "3.2.13", "size": 0, "available": True},

    # —— Windows (через Wine) ——
    {"id": "notepadpp-win", "apk": "", "name": "Notepad++", "pub": "Don Ho", "cat": "Утилиты",
     "desc": "Редактор текста Windows (Wine, portable)", "iconKind": "notes",
     "source": "windows", "platform": "windows", "format": "zip", "featured": True, "launchId": "pkg",
     "url": "https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.7.5/npp.8.7.5.portable.x64.zip",
     "exe": "notepad++.exe", "version": "8.7.5", "size": 0, "available": True},
    {"id": "putty-win", "apk": "", "name": "PuTTY", "pub": "Simon Tatham", "cat": "Интернет",
     "desc": "SSH/Telnet-клиент Windows (Wine)", "iconKind": "term",
     "source": "windows", "platform": "windows", "format": "exe", "portable": True, "launchId": "pkg",
     "url": "https://the.earth.li/~sgtatham/putty/latest/w64/putty.exe",
     "exe": "putty.exe", "version": "latest", "size": 0, "available": True},
    {"id": "7zip-win", "apk": "", "name": "7-Zip (Windows)", "pub": "Igor Pavlov", "cat": "Утилиты",
     "desc": "Архиватор 7-Zip для Windows через Wine", "iconKind": "files",
     "source": "windows", "platform": "windows", "format": "exe", "portable": True, "launchId": "pkg",
     "url": "https://www.7-zip.org/a/7za.exe",
     "exe": "7za.exe", "version": "extra", "size": 0, "available": True},
    {"id": "winscp-win", "apk": "", "name": "WinSCP", "pub": "Martin Prikryl", "cat": "Интернет",
     "desc": "SFTP/SCP-клиент Windows (Wine, portable)", "iconKind": "files",
     "source": "windows", "platform": "windows", "format": "zip", "launchId": "pkg",
     "url": "https://winscp.net/download/WinSCP-6.3.6-Portable.zip",
     "exe": "WinSCP.exe", "version": "6.3.6", "size": 0, "available": True},
]


def enrich_from_alpine(apps: list[dict]) -> list[dict]:
    branch = build.detect_branch()
    branch_root = f"https://dl-cdn.alpinelinux.org/alpine/{branch}"
    by_name, _ = build.load_indexes(branch_root)
    out: list[dict] = []
    for app in apps:
        item = dict(app)
        item.setdefault("price", "Бесплатно")
        src = item.get("source")
        if src in ("linux", "windows", "web"):
            item.setdefault("platform", "linux" if src == "linux" else ("windows" if src == "windows" else "web"))
            item.setdefault("launchId", "pkg" if src in ("linux", "windows") else "browser")
            item.setdefault("available", True)
            out.append(item)
            continue
        item.setdefault("source", "alpine" if item.get("apk") else "web")
        item.setdefault("platform", "alpine" if item.get("apk") else "web")
        item.setdefault("launchId", "pkg" if item.get("apk") else "browser")
        apk_name = (item.get("apk") or "").strip()
        if apk_name and apk_name in by_name:
            pkg = by_name[apk_name]
            item["version"] = pkg.get("V") or ""
            item["size"] = int(pkg.get("S") or 0)
            item["repo"] = pkg.get("repo") or "community"
            item["url"] = f"{pkg.get('repo_base')}/{apk_name}-{pkg.get('V')}.apk"
            item["available"] = True
        elif apk_name:
            # пакет заявлен, но в текущем Alpine нет — оставляем web/install best-effort
            item["available"] = False
            item["version"] = item.get("version") or ""
            if item.get("homeUrl") and item.get("source") != "web":
                # всё равно пробуем apk; если нет — пользователь увидит ошибку или web
                pass
        else:
            item["available"] = True
            item["source"] = "web"
            item["platform"] = "web"
        out.append(item)
    return out


def build_catalog() -> dict:
    apps = enrich_from_alpine(CURATED)
    # featured first
    apps.sort(key=lambda a: (0 if a.get("featured") else 1, a.get("name", "").lower()))
    cats = []
    for a in apps:
        c = a.get("cat")
        if c and c not in cats:
            cats.append(c)
    return {
        "generated": build.GTOS_VERSION,
        "alpine": build.detect_branch(),
        "source": "curated+alpine+linux+windows",
        "platforms": ["all", "alpine", "linux", "windows", "web"],
        "count": len(apps),
        "categories": ["all", *cats],
        "apps": apps,
    }


def main() -> int:
    build.log("generate curated GT Store catalog")
    catalog = build_catalog()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(catalog, ensure_ascii=False, indent=2)
    OUT_JSON.write_text(text + "\n", encoding="utf-8")
    OUT_SHARE.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    build.log(f"wrote {OUT_JSON} ({catalog['count']} apps)")
    missing = [a["id"] for a in catalog["apps"] if a.get("apk") and not a.get("available")]
    if missing:
        build.log("no alpine package for: " + ", ".join(missing[:20]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
