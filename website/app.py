#!/usr/bin/env python3
"""Официальный сайт GT/OS — Flask."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import json

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from markupsafe import Markup, escape

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "out"
DATA = ROOT / "data"
STORE_CATALOG = ROOT / "static" / "store" / "catalog.json"
BLOG_POSTS = DATA / "blog_posts.json"
COMMUNITY_DB = DATA / "community.db"

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "gtos-site-local-2026"


def load_store_catalog() -> dict:
    if not STORE_CATALOG.is_file():
        return {"count": 0, "apps": [], "categories": ["all"]}
    return json.loads(STORE_CATALOG.read_text(encoding="utf-8"))


def load_blog_posts() -> list[dict]:
    if not BLOG_POSTS.is_file():
        return []
    posts = json.loads(BLOG_POSTS.read_text(encoding="utf-8"))
    return sorted(posts, key=lambda p: p.get("date") or "", reverse=True)


def get_blog_post(slug: str) -> dict | None:
    for post in load_blog_posts():
        if post.get("slug") == slug:
            return post
    return None


def _inline_md(text: str) -> str:
    """Escape text with simple **bold** and [label](url)."""

    def link_sub(m: re.Match[str]) -> str:
        href = m.group(2).strip()
        if not (href.startswith("/") or href.startswith("https://") or href.startswith("http://")):
            return escape(m.group(0))
        return f'<a href="{escape(href)}">{escape(m.group(1))}</a>'

    parts = re.split(r"(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))", text)
    html: list[str] = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            html.append(f"<strong>{escape(part[2:-2])}</strong>")
        elif part.startswith("[") and "](" in part:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            html.append(link_sub(m) if m else escape(part))
        else:
            html.append(escape(part))
    return "".join(html)


def render_blog_body(paragraphs: list[str]) -> Markup:
    chunks: list[str] = []
    for raw in paragraphs or []:
        text = (raw or "").strip()
        if not text:
            continue
        if text.startswith("## "):
            chunks.append(f"<h2>{escape(text[3:].strip())}</h2>")
            continue
        chunks.append(f"<p>{_inline_md(text)}</p>")
    return Markup("\n".join(chunks))


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DATA.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(COMMUNITY_DB)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_community_db() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(COMMUNITY_DB)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_replies_thread ON replies(thread_id);
        """
    )
    count = db.execute("SELECT COUNT(*) AS c FROM threads").fetchone()["c"]
    if count == 0:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        seeds = [
            (
                "Магазин: Telegram, Chrome и VLC",
                "misha",
                "В каталоге оставили только нормальные приложения. Кто уже ставил VLC или GIMP из сети — отпишитесь, как прошло.",
            ),
            (
                "QEMU и загрузка с ISO",
                "alex",
                "Если зависает на Booting from ROM — проверьте, что не монтируете старый ISO как единственную загрузку. Актуальный образ: 1.6.",
            ),
            (
                "Идеи к 1.6",
                "сообщество",
                "Что хотите следующим: уведомления как в Win11, больше приложений в магазине, проще установка на диск? Пишите ответы в этой теме.",
            ),
        ]
        for title, author, body in seeds:
            cur = db.execute(
                "INSERT INTO threads (title, author, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (title, author, body, now, now),
            )
            db.execute(
                "INSERT INTO replies (thread_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (cur.lastrowid, "GT/OS", "Тема открыта — отвечайте прямо здесь, сообщения сохраняются у всех.", now),
            )
        db.commit()
    db.close()


init_community_db()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: str, max_len: int) -> str:
    text = (value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]


def clean_author(value: str) -> str:
    name = re.sub(r"\s+", " ", (value or "").strip())
    name = re.sub(r"[^\w\sА-Яа-яЁё.\-]", "", name, flags=re.UNICODE)
    return name[:40] or "гость"


def avatar_letter(name: str) -> str:
    for ch in (name or "").strip():
        if ch.isalnum():
            return ch.upper()
    return "?"


def format_when(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ts
    local = dt.astimezone()
    return local.strftime("%d.%m.%Y %H:%M")


app.jinja_env.globals["avatar_letter"] = avatar_letter
app.jinja_env.globals["format_when"] = format_when
app.jinja_env.globals["render_blog_body"] = render_blog_body

RELEASES = [
    {
        "id": "1.6",
        "label": "GT/OS Desktop 1.6 (x86_64)",
        "tag": "Текущий",
        "current": True,
        "summary": "UEFI+BIOS, HiDPI, онбординг, обновления, SHA256, сон с сетью, звук.",
        "filename": "GTOS-1.6-x86_64.iso",
    },
    {
        "id": "1.5.6",
        "label": "GT/OS Desktop 1.5.6 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Ctrl+Alt+Delete, индикатор операций, бэкапы по расписанию, экономия заряда и тихие часы.",
        "filename": "GTOS-1.5.6-x86_64.iso",
    },
    {
        "id": "1.5.4",
        "label": "GT/OS Desktop 1.5.4 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Wi‑Fi с памятью, буфер X11, D-Bus-уведомления, ассоциации файлов, CUPS, мультипользователи.",
        "filename": "GTOS-1.5.4-x86_64.iso",
    },
    {
        "id": "1.5.3",
        "label": "GT/OS Desktop 1.5.3 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Медиа, Bluetooth, бэкапы; UEFI/GPT, PNG‑снимки, ALSA, сон и обновление оболочки.",
        "filename": "GTOS-1.5.3-x86_64.iso",
    },
    {
        "id": "1.5.2",
        "label": "GT/OS Desktop 1.5.2 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "GT Power Manager, обновлённая сеть в Параметрах, GT Archive Manager и GT Font Manager.",
        "filename": "GTOS-1.5.2-x86_64.iso",
    },
    {
        "id": "1.5.1",
        "label": "GT/OS Desktop 1.5.1 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "GT Control Center и Diagnostics, Update Engine с безопасным откатом, GT Security и GT Recovery.",
        "filename": "GTOS-1.5.1-x86_64.iso",
    },
    {
        "id": "1.5",
        "label": "GT/OS Desktop 1.5 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Магазин с Telegram, Chrome, VLC и другими нужными приложениями; uptime в терминале и доработанная верхняя панель.",
        "filename": "GTOS-1.5-x86_64.iso",
    },
    {
        "id": "1.4",
        "label": "GT/OS Desktop 1.4 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Пуск Deepin, блокнот с вкладками, шрифты сайта, проводник с избранным, графики в диспетчере и браузер с CSS и закладками.",
        "filename": "GTOS-1.4-x86_64.iso",
    },
    {
        "id": "1.3",
        "label": "GT/OS Desktop 1.3 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "GT Search, Snap Layouts, буфер 2.0, виртуальные столы, Центр обновлений, Storage и конфиденциальность.",
        "filename": "GTOS-1.3-x86_64.iso",
    },
    {
        "id": "1.2",
        "label": "GT/OS Desktop 1.2 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Двенадцать удобств как в Windows: панель задач, Alt+Tab, буфер Win+V, снимки, блокировка, ночной свет и горячие клавиши.",
        "filename": "GTOS-1.2-x86_64.iso",
    },
    {
        "id": "1.1",
        "label": "GT/OS Desktop 1.1 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Повседневный стол: установщик на диск, проводник в стиле Windows, параметры, браузер по сети и постоянный том.",
        "filename": "GTOS-1.1-x86_64.iso",
    },
    {
        "id": "1.0",
        "label": "GT/OS Desktop 1.0 (x86_64)",
        "tag": "Архив",
        "current": False,
        "summary": "Первый публичный выпуск: Linux + Qt 6, Пуск, док, терминал, проводник и официальный ISO x86_64.",
        "filename": "GTOS-1.0-x86_64.iso",
    },
]

CHANGELOG = [
    {
        "version": "1.6",
        "date": "7 ноября 2026",
        "tag": "Текущий",
        "title": "UEFI, HiDPI и основа «настоящей» ОС",
        "changes": [
            "ISO грузится в BIOS и UEFI (El Torito EFI + /EFI/BOOT/BOOTX64.EFI)",
            "Рядом с каждым ISO — файл .sha256 для проверки образа",
            "Масштаб интерфейса 100/125/150/200% (HiDPI) в Параметрах",
            "Первый запуск: 4 шага — учётка, язык, сеть, бэкапы/советы",
            "Центр обновлений: проверить → установить → установить и перезагрузить",
            "Сон: после пробуждения сеть и звук поднимаются снова",
            "Звук по умолчанию: Master/PCM unmuted при старте сеанса",
            "Safe Mode, Ctrl+Alt+Delete и бэкапы из 1.5.6 сохранены",
            "В Магазине: Cursor (Linux AppImage)",
        ],
    },
    {
        "version": "1.5.6",
        "date": "3 ноября 2026",
        "tag": "Архив",
        "title": "Безопасный стол и повседневные операции",
        "changes": [
            "Ctrl+Alt+Delete: полноэкранный безопасный стол поверх всех окон (также Ctrl+Alt+End / Backspace в QEMU)",
            "Блокировка, смена пользователя, выход, диспетчер задач, перезагрузка и выключение из безопасного стола",
            "Индикатор незавершённых загрузок и операций в панели задач с прогрессом",
            "Резервное копирование по расписанию: ежедневно или еженедельно",
            "Экономия заряда и тихие часы в быстрых настройках",
            "Автоблокировка при бездействии (5 / 15 / 30 мин)",
            "Очистка диска: временные файлы и корзина одной кнопкой",
            "Быстрая заметка по Meta+N — сохраняется в Документы",
            "Безопасный режим загрузки: пункт Safe Mode в ISO/GRUB, python run.py --safe, перезагрузка из Ctrl+Alt+Delete",
            "Продукт опубликован от Glukhov Mikhail (вместо Glukhov Technologies)",
        ],
    },
    {
        "version": "1.5.4",
        "date": "31 октября 2026",
        "tag": "Архив",
        "title": "Галерея и Погода",
        "changes": [
            "Галерея: библиотека изображений, альбомы и избранное, полноэкранный просмотр и слайд-шоу",
            "Галерея: сведения о файле, поворот и отражение; без зелёного затемнения при открытии снимка",
            "Контекстное меню Проводника: открытие в Галерее",
            "Погода: текущая погода, почасовой прогноз на 24 часа и прогноз на 7 дней (Open-Meteo)",
            "Погода: яркий интерфейс по коду погоды, прокрутка без выхода за рамки окна",
            "Шторка уведомлений: красочный виджет погоды (без «битых» эмодзи) с переходом в Погоду",
            "Приложения переименованы: Галерея, Погода, Медиаплеер",
            "Английская раскладка в QEMU: XKB us + корректный маппинг клавиш",
            "Новые иконки DeskIconArt для Галереи и Погоды",
            "Контрольный центр: двойной клик по устройству открывает окно «Свойства»",
            "GT Document Viewer: просмотр PDF (рендер страниц через poppler)",
            "«Открыть с помощью»: выбор любой программы из списка приложений",
            "Неизвестный тип файла — белый листок; при открытии предлагается выбрать программу",
            "Больше иконок DeskIconArt: PDF, USB, ZIP, шрифт, сеть, Bluetooth, питание и др.",
            "Wi‑Fi: сети сохраняются и поднимаются после перезагрузки",
            "poppler-utils, xclip, dbus/dunst и CUPS в образе",
            "Общий буфер обмена с X11-приложениями (Firefox и др.)",
            "Уведомления внешних приложений через dunst → шторка GT/OS",
            "Ассоциации файлов «всегда открывать с…» сохраняются",
            "Оболочка автоматически перезапускается при падении",
            "Печать через CUPS (lp); Magazin не считает пустой код apk успехом",
            "Обновление оболочки по сети (URL канала) + ISO/USB",
            "Несколько учётных записей: создание и переключение сеанса",
            "Корзина: перетаскивание файлов и папок со стола и из Проводника",
            "Корзина: контекстное меню (открыть, очистить, закрепить, свойства)",
            "Галерея: аккуратный сайдбар альбомов и сетка снимков",
            "Просмотр фото: панель как в Windows Photos, векторные иконки, зум и сведения",
            "Галерея: масштаб фото колёсиком мыши",
            "Галерея: увеличенное фото не выходит за рамки окна, можно двигать мышью",
            "Магазин: установка не только Alpine — Linux (AppImage/deb) и Windows (Wine)",
            "Магазин: фильтр платформ Alpine / Linux / Windows / Веб",
            "Быстрые настройки: новый вид с иконками, громкостью и яркостью",
        ],
    },
    {
        "version": "1.5.3",
        "date": "31 октября 2026",
        "tag": "Архив",
        "title": "Media, Bluetooth, Backups, UEFI",
        "changes": [
            "GT Media Player: Play/Pause, Stop, перемотка, громкость, название и длительность; открытие медиа из Проводника",
            "Параметры → Bluetooth: реальное обнаружение через bluetoothctl, сопряжение, подключение/отключение и ошибки",
            "Контрольный центр → Бэкапы: создание и восстановление копий Документов, Загрузок и рабочего стола",
            "Рамки внешних окон (Firefox и др.) совпадают с заголовком QML‑окон: #2d2d2d, красный крестик, без Linux Clearlooks",
            "Firefox: исправлен ложный «уже запущен»; QEMU 14 ГБ ОЗУ и увеличенные кэши браузера",
            "Экран блокировки: анимации часов/логина/аватара на месте; обои JPEG не анимируются (это и давало зависание на TCG)",
            "Поиск в Пуске снова простой фильтр списка приложений, как раньше",
            "Установщик: GPT + UEFI (и hybrid BIOS), автоопределение прошивки; режим Авто / UEFI / BIOS / Оба",
            "Снимок экрана (PrtSc / Win+Shift+S) сохраняет настоящий PNG в «Изображения»",
            "Системная громкость в трее и Параметрах управляет ALSA (amixer Master/PCM)",
            "Update Engine обновляет не только apk, но и оболочку/initrd с ISO или USB (gtos-shell-update)",
            "Пароль сессии хранится как SHA‑256 с солью, не открытым текстом в desktop.conf",
            "Сон: крышка ноутбука и кнопка «Усыпить сейчас» пишут mem/freeze в /sys/power/state",
            "Диагностика: проверка Wi‑Fi, звука, GPU, Bluetooth и USB‑носителя (отчёт в Документах)",
            "Сайт: переработаны «Что нового», «Продукт», поддержка/FAQ и служебные страницы под 1.5.3",
            "Выпуск 1.5.2 перенесён в архив загрузок",
        ],
    },
    {
        "version": "1.5.2",
        "date": "31 октября 2026",
        "tag": "Архив",
        "title": "Power, Network, Apps, Fluent tools",
        "changes": [
            "GT Power Manager: производительность, баланс, энергосбережение, крышка ноутбука и статистика батареи",
            "Параметры → Система: быстрый вход в Power Manager и настройку крышки",
            "Параметры → Сеть: Wi‑Fi и Ethernet, сохранённые подключения, IP/DNS, трафик и диагностика",
            "GT Archive Manager: ZIP, TAR, GZIP и 7Z — создать и распаковать",
            "Проводник: «Сжать в архив» и «Распаковать» в контекстном меню",
            "GT Font Manager: превью .ttf/.otf при открытии шрифта и установка в систему",
            "Исправлена ошибка загрузки интерфейса после обновления раздела «Сеть» (система снова стартует)",
            "GT Power Manager встроен в Параметры → Питание: режимы, крышка и батарея без отдельного окна",
            "GT Recovery перенесён в Контрольный центр; Power Manager и Recovery убраны из списка приложений Пуска",
            "Центр уведомлений: убрана зелёная полоса поверх скругления; тосты и карточки обновлены",
            "Контекстное меню «Свойства»: окно как в проводнике — тип, размер, даты, атрибуты, ОКки",
            "Firefox: стабильный запуск без dbus-run-session, software GL и ожидание на медленном TCG",
            "Оболочка больше не полноэкранный слой поверх окон: Firefox и другие программы видны поверх рабочего стола",
            "Сторонние приложения показывают свою иконку из пакета, а не общую иконку GT/OS",
            "Параметры → Приложения: поиск и фильтр «Приложения GT» / «Сторонние»",
            "Калькулятор: оператор больше не обнуляет дисплей; строка выражения и клавиатура",
            "Календарь: сетка дней, выбор даты и заметка дня с сохранением",
            "Почта: папки, список черновиков из Документов и редактор в три колонки",
            "Магазин: поиск, категории-чипы, сетка карточек и страница приложения без «кислотного» кабинета",
            "Сайт: на главной снова коробка ISO с USB‑ключом вместо promo‑обложки",
            "Сайт: футер на всю ширину экрана",
            "Сайт: страницы «Что нового», «Советы», «Требования», «Конфиденциальность» и «Доступность»",
            "Док: кнопка «Свернуть все окна» с SVG‑иконкой (Win+D)",
            "Рабочие пространства: новая сетка превью, переименование и удаление столов",
            "Рабочие пространства реально разделяют окна между столами; активное окно можно перенести",
            "Иконки рабочего стола свои у каждого пространства: на «Разработка» и других нет ярлыков основного стола",
            "Магазин: сторонние программы снова открываются — если файлы пакета пропали после перезагрузки, они тихо догружаются из кэша и запускаются сами",
            "Firefox и другие внешние программы запускаются надёжно даже без setsid (запасной путь nohup/подоболочка), раньше кнопка «Открыть» могла молча ничего не делать",
            "Исправлено: Firefox снова реально стартует (ложный «уже запущен» из‑за самосовпадения pgrep)",
            "Рамки внешних окон (Firefox и др.) в стиле GT/OS: тёмный Fluent‑заголовок вместо Linux Clearlooks",
            "QEMU: 14 ГБ ОЗУ; Firefox получил увеличенные кэши и меньше content‑процессов — меньше лагов на TCG",
            "Выпуск 1.5.1 перенесён в архив загрузок",
        ],
    },
    {
        "version": "1.5.1",
        "date": "30 октября 2026",
        "tag": "Архив",
        "title": "Control Center, Security, Recovery",
        "changes": [
            "GT Control Center: устройства, службы, драйверы, фоновые процессы и состояние компонентов",
            "GT Diagnostics внутри Control Center: диски, ОЗУ, драйверы, журнал ошибок и отчёт об оборудовании",
            "Открытие Control Center из Пуска и по ПКМ на «Мой компьютер»",
            "GT Update Engine в Параметры → Центр обновления: проверка, зависимости, установка и история",
            "Безопасный откат обновлений по снимку зависимостей пакетов, без слепого удаления",
            "GT Security в Параметры → Безопасность: разрешения, автозапуск, аудит и права пользователя",
            "GT Recovery: точки восстановления, копии данных пользователя и возврат после неудачного обновления",
            "Выпуск 1.5 перенесён в архив загрузок",
            "Сайт: живое сообщество с темами и ответами в общей базе",
            "Сайт: полноценный блог с постами; промо выпуска на блоге и в списке изменений",
            "Страница изменений: компактный журнал версий, архив свёрнут",
            "Control Center: диагностика внутри окна, без кнопки за краем экрана",
            "Control Center и Диспетчер задач оформлены как Параметры: боковая панель и карточки",
            "Блог: удобнее главная — свежий пост слева/справа и сетка остальных записей",
            "Контрольный центр: своя иконка, раздел «Устройства» с реальным деревом оборудования",
            "Диспетчер задач: таблица процессов как в Windows 11 — поиск, завершение, подсветка нагрузки",
            "Страница поддержки собрана заново: путь «поставить → разобраться → спросить», карта тем 1.5.1 и форма связи",
            "Контрольный центр: новая иконка в стиле остальных значков; устройства — плотное дерево как в диспетчере устройств",
            "Блог: у постов разные обложки, а не один и тот же промо-кадр 1.5.1",
            "Эмулятор QEMU: 10 ГБ ОЗУ, постоянный диск от 16 ГБ; русская раскладка через X11",
            "Страница «Разработчикам»: сначала архив исходников, потом сборка и QEMU — не команды «из воздуха»",
            "Запуск приложений из магазина больше не блокирует интерфейс ожиданием в sys.run",
            "Параметры: снова показывают содержимое разделов (починена пустая «Главная»)",
            "Отзывчивость: убраны ping/du/iw с панели и из Параметров; батарея и Wi‑Fi читаются из /sys без shell; сеть без зависаний на 2 с",
            "Контрольный центр открывается сразу с лёгкими данными, полный опрос железа — чуть позже",
            "Таймаут системных команд сокращён: длинный shell больше не держит весь интерфейс десятки секунд",
            "Параметры грузят только открытый раздел — остальное не создаётся в памяти сразу",
            "Панель и сеть опрашиваются реже и без лишнего shell — меньше подвисаний в эмуляторе",
        ],
    },







    {
        "version": "1.5",
        "date": "28 октября 2026",
        "tag": "Архив",
        "title": "Магазин, uptime и рабочие пространства",
        "changes": [
            "Магазин GT: сторонние приложения (Firefox, VLC, GIMP, LibreOffice и др.)",
            "Терминал: uptime считается по /proc/uptime (с запасным таймером сессии)",
            "Дата в панели больше не сливается с годом",
            "Кнопка «Рабочий стол» в доке открывает рабочие пространства, иконка outline",
            "Выпуск 1.4 перенесён в архив загрузок",
            "ПКМ по иконке в доке: меню «закрепить / закрыть окно»",
            "Иконки рабочего стола больше не мигают при перетаскивании и открытии окон",
            "Telegram из магазина открывает веб-клиент, а не Почту",
            "Блокнот в зелёном стиле GT/OS",
            "Пуск: Montserrat Regular/SemiBold вместо подстановки DejaVu",
            "Меню Пуск поверх открытых окон",
            "Просмотр PNG/JPG: приложение «Фотографии» и контекстное меню для картинок",
            "Раскладка РУС/ENG в правом нижнем углу, ввод кириллицы в полях",
            "Быстрые настройки, буфер обмена, умный док и «Этот компьютер» обновлены",
            "Магазин: новое боковое меню и страница «О приложении»",
            "Клевер без стебля; курсоры как в Windows (стрелка, рука, I‑beam, resize)",
            "Индикатор РУС/ENG в правом нижнем углу без рамки",
            "Открытие приложений из магазина в отдельном окне со своим названием",
            "Индикатор РУС крупнее и с отступами над доком",
            "Магазин: только нужные приложения (Telegram, Chrome, VLC, GIMP…), без мусора Alpine",
            "Установка из магазина качает реальные пакеты (apk) из репозиториев",
            "Сайт: заново собраны страницы «Блог» и «Сообщество»",
            "Переключатель РУС/ENG перенесён в верхний левый угол панели",
            "Блог — редакционная вёрстка; сообщество — доска обсуждений; разработчикам — мастерская, не копия «Скачать»",
            "Сайт: единые кнопки-капсулы, круглая иконка GT; шапка не пропадает на внутренних страницах",
            "Сообщество: каналы в том же стиле карточек, что блок «Система целиком» на главной",
            "Разработчикам снова компактная страница со скриптами и путями — удобнее для сборки",
            "В меню вместо «О нас» — «Ещё» с выпадающим списком (туда можно добавлять новые разделы)",
            "Ядро linux-lts и firmware для ПК (Wi‑Fi, GPU, звук), а не только virt для QEMU",
            "ISO загружается с флешки (BIOS / Isolinux); установка копирует систему на диск и ставит GRUB",
            "В образе: Firefox, ALSA, wpa_supplicant; центр обновлений проверяет пакеты через apk",
            "Обои снова в образе после полной сборки (и при каждой следующей build/refresh_ui)",
            "Сторонние приложения (Firefox и др.) видны в Пуске и в списке установленных",
            "Firefox открывается как настоящее окно Mozilla (профиль в /var/lib/gtos, без заглушки GT)",
            "Проводник: цветные иконки на ленте команд; в диспетчере задач — иконки в боковом меню",
            "Загрузка модулей через modprobe (меньше ошибок в логе после перехода на linux-lts)",
            "В QEMU рабочий стол на software-рендере — без сбоев из‑за virtio_gpu без 3D",
            "Проводник снова открывается: убрано несуществующее свойство у иконок ленты",
            "В трее: уровень Wi‑Fi, громкости и батареи; цвет батареи меняется при разряде",
            "Кабель в трее — иконка монитора с RJ45 без подписи LAN; у громкости без процента снизу",
            "Иконка кабеля в трее перерисована: штекер RJ45 с защёлкой, не отдельный квадрат",
            "Быстрые настройки как панель: плитки, громкость, буфер и блок; сеть открывает список реальных Wi‑Fi",
            "Иконка кабеля в трее — штекер RJ45 с контактами и хвостом провода",
            "Лента проводника: цветные иконки DeskIconArt над Создать / Копировать / Вставить и др.",
            "Firefox открывается от пользователя со своим профилем; Openbox даёт окнам крестик и заголовок",
            "Иконка кабеля в трее перерисована контуром монитора и штекера — больше не похожа на «П»",
            "Сеть по кабелю в трее — порт RJ45 как в Windows/Material, без монитора",
            "Иконка кабеля в трее без размытия: простые фигуры вместо Canvas",
            "Иконка кабеля в трее — монитор и штекер точно по образцу",
            "Диспетчер задач: только окна и понятные программы, без потоков ядра; новый дизайн GT/OS",
            "Параметры → Память: категории с полосками, контроль памяти и очистка — как в Windows",
            "В «Памяти» снова сверху цветная карта диска вместе с категориями",
            "Экран загрузки: текстовый знак GT/OS с появлением и тонкая полоска туда‑сюда",
            "Параметры → О системе: карточки диска/ОЗУ/ЦП/графики, сведения об устройстве и GT/OS",
            "Загрузка больше не зависает: тяжёлый старт после анимации, плавный переход к блокировке",
            "Исправлен синтаксис Main.qml — рабочий стол снова запускается",
            "Firefox: надёжный запуск от пользователя без сбоя setpriv",
            "ПКМ по файлу/папке: меню как в Windows, лишние пункты скрыты (не серые)",
            "Firefox: profiles.ini, su-exec из /sbin, software GL — снова должен открываться",
            "Центр уведомлений: новый дизайн — секции «Сейчас»/«Ранее», иконки и пустое состояние",
        ],
    },
    {
        "version": "1.4",
        "date": "28 октября 2026",
        "tag": "Архив",
        "title": "Пуск Deepin, блокнот, проводник и браузер",
        "changes": [
            "Шрифты: Montserrat для интерфейса (кириллица вместо DejaVu), Syne для заголовков, Cascadia Mono для кода",
            "Обновлённый пуск: категории, список приложений, частое и недавно установленное",
            "Блокнот с вкладками, меню «Файл / Изменить / Просмотр» и сохранением по Ctrl+S",
            "Больше анимаций интерфейса: окна, док, панели, поиск и Alt+Tab",
            "Проводник: вкладки папок и избранное в боковой панели",
            "Диспетчер задач: плавные графики ЦП и памяти, иконки приложений у процессов",
            "Браузер: улучшенный CSS-рендеринг страниц и панель закладок",
            "Единые иконки приложений как на рабочем столе — в Пуске, доке, диспетчере и окнах",
            "Иконки DeskIconArt везде вместо цветных квадратов: магазин, параметры, проводник, поиск",
            "Пуск в зелёной стилистике GT/OS, исправлено масштабирование иконок",
            "Логотип GT — клевер акцентным цветом; кнопки питания и разворота без жёлтых артефактов",
            "Диспетчер задач: список процессов без иконок",
            "Рабочий стол: создание файлов и папок, перетаскивание значков с сохранением позиций",
            "Подсказки при наведении на док; виртуальные столы перенесены в верхнюю панель",
            "Единая системная иконка для обновлений, Storage и конфиденциальности",
            "Понятный экран загрузки с процентами; ВМ запускается с 5 ГБ ОЗУ",
            "Установщик GT/OS 1.4: тёмный интерфейс, шаги слева, клевер и акцент системы",
            "Контекстное меню как в Windows: открыть, блокнот, вырезать/копировать, ярлык, свойства",
            "Параметры → Главная: карточки устройства, сети, обновлений, звука и персонализации",
            "Параметры: разделы Память, Конфиденциальность и Центр обновления вместо отдельных приложений",
            "Раздел «О системе»: карточка GT/OS с клевером, ядром и зелёной кнопкой сохранения",
            "Параметры: обновлены Центр обновления, Сеть, Приложения (список) и Учётные записи",
            "В Параметрах везде акцент GT вместо синего Windows",
            "Верхняя панель: у правого края время, рядом дата («24 мая 2025 года»), затем уведомления и трей",
            "Верхняя панель: монохромные иконки, батарея ноутбука, попап рабочих пространств вместо переключателей",
            "Мягкое затемнение сверху вместо полоски; добавлены новые обои рабочего стола",
        ],
    },
    {
        "version": "1.3",
        "date": "27 октября 2026",
        "tag": "Архив",
        "title": "Центр уведомлений, диспетчер задач и умный док",
        "changes": [
            "Шторка уведомлений с историей (как в Windows)",
            "Диспетчер задач в стиле Windows 11: процессы, ЦП, память, автозагрузка",
            "Менеджер автозагрузки внутри диспетчера задач",
            "Браузер: вкладки, строка поиска Google и читаемый вид страниц",
            "Главные страницы Google и Яндекса открываются с нормальной вёрсткой",
            "Верхняя панель: только трей и часы",
            "GT Search (Win+S) и GT Command (Alt+Space)",
            "Snap Layouts — раскладки окон",
            "Буфер обмена 2.0: закрепление и поиск (Win+V)",
            "Виртуальные столы: Работа, Разработка, Развлечения",
            "Центр обновлений GT, GT Storage и Центр конфиденциальности",
            "Медиаплеер: плейлисты и библиотека из ~/Музыка",
            "Умный док предлагает закрепить часто используемые приложения",
            "На сайте доступен архив ISO 1.2",
        ],
    },
    {
        "version": "1.2",
        "date": "26 октября 2026",
        "tag": "Архив",
        "title": "Удобства как в Windows 10/11",
        "changes": [
            "Панель задач с открытыми окнами и индикатором активного приложения",
            "Переключатель окон Alt+Tab",
            "«Показать рабочий стол» (кнопка на панели / Win+D)",
            "История буфера обмена (Win+V)",
            "Календарь по клику на часы в трее",
            "Иконки на столе: Этот компьютер, Файлы, Корзина, Параметры",
            "Снимок экрана (PrtSc / Win+Shift+S) с сохранением в «Изображения»",
            "Закрепление и открепление приложений на панели задач",
            "Ночной свет и быстрое выключение звука («Без звука»)",
            "Редактируемая адресная строка в проводнике",
            "Горячие клавиши: Win+L (блокировка), Win+E (файлы), Win+I (параметры), Esc",
            "Блокировка экрана и тёмное контекстное меню рабочего стола",
            "Свой экран загрузки и мастер первого пользователя",
            "На сайте: архив ISO 1.1, обновлённый футер и центр поддержки",
        ],
    },
    {
        "version": "1.1",
        "date": "октябрь 2026",
        "tag": "Архив",
        "title": "Повседневный рабочий стол",
        "changes": [
            "Графический установщик на диск из Пуска: язык → диск → пользователь → подтверждение",
            "Установщик размечает диск, копирует систему и ставит загрузчик",
            "Проводник в светлом стиле Windows: лента, адресная строка, «Быстрый доступ» и «Этот компьютер»",
            "Таблица файлов: имя, дата, тип и размер",
            "Параметры в стиле Windows 11",
            "Браузер: загрузка страниц по сети и показ с разметкой",
            "Сетевые и дисковые инструменты в образе (iproute2, curl, e2fsprogs и установка на том)",
            "Постоянный том пользователя: файлы и настройки сохраняются между перезапусками",
            "Приветственный документ «Добро пожаловать в GT/OS 1.1» в Документах",
            "На сайте: инструкция ISO → USB (Ventoy/Rufus) → установка на ПК",
        ],
    },
    {
        "version": "1.0",
        "date": "октябрь 2026",
        "tag": "Архив",
        "title": "Первый публичный выпуск",
        "changes": [
            "Экспериментальная основа собственного рабочего стола GT/OS",
            "Ядро Linux и оболочка на Qt 6 (QML), упакованные в initramfs",
            "Официальный загрузочный ISO x86_64",
            "Пуск и док с базовыми приложениями рабочего стола",
            "Терминал с прямым доступом к системе",
            "Проводник файлов в первой редакции",
            "Официальный сайт с загрузкой образа и описанием системы",
        ],
    },
]


def human_size(num: int) -> str:
    if num <= 0:
        return "—"
    mb = num / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}".replace(".", ",") + " МБ"
    kb = num / 1024
    return f"{kb:.0f} КБ"


def release_info(meta: dict) -> dict:
    iso = OUT / meta["filename"]
    size = iso.stat().st_size if iso.is_file() else 0
    sha_path = Path(str(iso) + ".sha256")
    sha256 = ""
    if sha_path.is_file():
        sha256 = sha_path.read_text(encoding="utf-8", errors="replace").split()[0].strip()
    elif iso.is_file() and size > 0 and size < 900_000_000:
        # не считаем SHA на лету для огромных файлов без sidecar — только если есть .sha256
        sha256 = ""
    return {
        **meta,
        "ready": size > 0,
        "bytes": size,
        "size_label": human_size(size) if size else "собирается…",
        "size_bytes_label": f"{size:,} байт".replace(",", " ") if size else "",
        "name": meta["filename"],
        "path": iso,
        "sha256": sha256,
        "sha256_file": sha_path.name if sha_path.is_file() else "",
    }


def all_releases() -> list[dict]:
    return [release_info(r) for r in RELEASES]


def current_release() -> dict:
    for r in all_releases():
        if r.get("current"):
            return r
    return all_releases()[0]


def archives() -> list[dict]:
    return [r for r in all_releases() if not r.get("current")]


@app.route("/")
def home():
    return render_template(
        "index.html",
        page="home",
        title="GT/OS — официальный сайт",
        release=current_release(),
        iso=current_release(),
        releases=all_releases(),
    )


@app.route("/product")
def product():
    return render_template(
        "product.html",
        page="product",
        title="GT/OS — продукт",
        release=current_release(),
    )


@app.route("/download")
def download():
    releases = all_releases()
    current = current_release()
    return render_template(
        "download.html",
        page="download",
        title="Скачать GT/OS",
        release=current,
        releases=releases,
        archives=archives(),
        iso=current,
    )


@app.route("/changelog")
@app.route("/changes")
def changelog():
    return render_template(
        "changelog.html",
        page="changelog",
        title="Список изменений GT/OS",
        changelog=CHANGELOG,
        release=current_release(),
        promo_image="img/gtos-promo-1.5.6.jpg",
    )


@app.route("/blog")
def blog():
    posts = load_blog_posts()
    return render_template(
        "blog.html",
        page="blog",
        title="Блог GT/OS",
        release=current_release(),
        posts=posts,
        featured=posts[0] if posts else None,
    )


@app.route("/blog/<slug>")
def blog_post(slug: str):
    post = get_blog_post(slug)
    if not post:
        abort(404)
    return render_template(
        "blog_post.html",
        page="blog",
        title=f"{post['title']} — блог GT/OS",
        release=current_release(),
        post=post,
    )


@app.route("/community", methods=["GET", "POST"])
def community():
    db = get_db()
    if request.method == "POST":
        # honeypot
        if (request.form.get("website") or "").strip():
            return redirect(url_for("community"))
        title = clean_text(request.form.get("title", ""), 120)
        author = clean_author(request.form.get("author", ""))
        body = clean_text(request.form.get("body", ""), 4000)
        if len(title) < 4 or len(body) < 8:
            flash("Тема: минимум 4 символа в заголовке и 8 в тексте.", "error")
            return redirect(url_for("community") + "#new")
        now = utc_now()
        cur = db.execute(
            "INSERT INTO threads (title, author, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title, author, body, now, now),
        )
        db.commit()
        flash("Тема опубликована — её видят все.", "ok")
        return redirect(url_for("community_thread", thread_id=cur.lastrowid))

    rows = db.execute(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM replies r WHERE r.thread_id = t.id) AS reply_count
        FROM threads t
        ORDER BY t.updated_at DESC, t.id DESC
        """
    ).fetchall()
    return render_template(
        "community.html",
        page="community",
        title="Сообщество GT/OS",
        release=current_release(),
        threads=rows,
    )


@app.route("/community/t/<int:thread_id>", methods=["GET", "POST"])
def community_thread(thread_id: int):
    db = get_db()
    thread = db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
    if not thread:
        abort(404)

    if request.method == "POST":
        if (request.form.get("website") or "").strip():
            return redirect(url_for("community_thread", thread_id=thread_id))
        author = clean_author(request.form.get("author", ""))
        body = clean_text(request.form.get("body", ""), 4000)
        if len(body) < 2:
            flash("Напишите текст ответа.", "error")
            return redirect(url_for("community_thread", thread_id=thread_id) + "#reply")
        now = utc_now()
        db.execute(
            "INSERT INTO replies (thread_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (thread_id, author, body, now),
        )
        db.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))
        db.commit()
        flash("Ответ добавлен.", "ok")
        return redirect(url_for("community_thread", thread_id=thread_id) + "#replies")

    replies = db.execute(
        "SELECT * FROM replies WHERE thread_id = ? ORDER BY id ASC",
        (thread_id,),
    ).fetchall()
    return render_template(
        "community_thread.html",
        page="community",
        title=f"{thread['title']} — сообщество GT/OS",
        release=current_release(),
        thread=thread,
        replies=replies,
    )


@app.route("/gallery")
def gallery():
    return redirect(url_for("blog"))


@app.route("/about")
def about():
    return render_template(
        "about.html",
        page="about",
        title="О GT/OS",
        release=current_release(),
    )


@app.route("/whats-new")
def whats_new():
    return render_template(
        "whats_new.html",
        page="whats-new",
        title="Что нового в GT/OS",
        release=current_release(),
    )


@app.route("/tips")
def tips():
    return render_template(
        "tips.html",
        page="tips",
        title="Советы GT/OS",
        release=current_release(),
    )


@app.route("/requirements")
def requirements():
    return render_template(
        "requirements.html",
        page="requirements",
        title="Системные требования GT/OS",
        release=current_release(),
    )


@app.route("/privacy")
def privacy():
    return render_template(
        "privacy.html",
        page="privacy",
        title="Конфиденциальность GT/OS",
        release=current_release(),
    )


@app.route("/accessibility")
def accessibility():
    return render_template(
        "accessibility.html",
        page="accessibility",
        title="Специальные возможности GT/OS",
        release=current_release(),
    )


@app.route("/support")
def support():
    return render_template(
        "support.html",
        page="support",
        title="Поддержка GT/OS",
        release=current_release(),
    )


SOURCE_ZIP = "GTOS-source.zip"


def source_archive() -> dict:
    path = OUT / SOURCE_ZIP
    size = path.stat().st_size if path.is_file() else 0
    return {
        "filename": SOURCE_ZIP,
        "ready": size > 0,
        "size_label": human_size(size) if size else "ещё не собран",
        "bytes": size,
    }


@app.route("/developers")
def developers():
    return render_template(
        "developers.html",
        page="developers",
        title="Разработчикам GT/OS",
        release=current_release(),
        source=source_archive(),
    )


@app.route("/files/<path:name>")
def download_file(name: str):
    allowed = {r["filename"] for r in RELEASES}
    allowed |= {r["filename"] + ".sha256" for r in RELEASES}
    allowed.add(SOURCE_ZIP)
    if name not in allowed:
        abort(404)
    path = OUT / name
    if not path.is_file():
        abort(404)
    return send_from_directory(OUT, name, as_attachment=True)


@app.route("/iso/<path:name>")
def iso_file(name: str):
    return download_file(name)


@app.route("/get")
def get_iso():
    rel = current_release()
    if not rel.get("ready"):
        abort(404)
    return redirect(url_for("download_file", name=rel["filename"]))


@app.route("/api/store/catalog")
def api_store_catalog():
    data = load_store_catalog()
    q = (request.args.get("q") or "").strip().lower()
    cat = (request.args.get("cat") or "all").strip()
    limit = request.args.get("limit", type=int) or 0
    offset = request.args.get("offset", type=int) or 0
    apps = data.get("apps") or []
    if cat and cat != "all":
        apps = [a for a in apps if a.get("cat") == cat]
    if q:
        apps = [
            a
            for a in apps
            if q in (a.get("name") or "").lower()
            or q in (a.get("id") or "").lower()
            or q in (a.get("desc") or "").lower()
            or q in (a.get("pub") or "").lower()
        ]
    total = len(apps)
    if offset:
        apps = apps[offset:]
    if limit and limit > 0:
        apps = apps[:limit]
    return jsonify(
        {
            "count": total,
            "offset": offset,
            "limit": limit,
            "alpine": data.get("alpine"),
            "categories": data.get("categories") or ["all"],
            "apps": apps,
        }
    )


@app.route("/api/store/app/<app_id>")
def api_store_app(app_id: str):
    data = load_store_catalog()
    for app in data.get("apps") or []:
        if app.get("id") == app_id:
            return jsonify(app)
    abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
