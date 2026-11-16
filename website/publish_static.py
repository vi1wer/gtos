#!/usr/bin/env python3
"""Собрать статический сайт GT/OS для GitHub Pages (ветка gh-pages)."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "site-dist"

os.environ.setdefault("GTOS_SITE_PUBLIC", "1")
# Префикс Pages добавляем только при записи HTML (url_for остаётся от корня /)
os.environ.pop("GTOS_SITE_PREFIX", None)

PAGES_PREFIX = "/gtos"

# Импорт после env — app читает флаги при загрузке
sys.path.insert(0, str(ROOT))
from app import app, get_db, init_community_db, load_blog_posts  # noqa: E402


def page_path(url_path: str) -> Path:
    p = url_path.strip("/")
    if not p:
        return DIST / "index.html"
    # /blog/slug → blog/slug/index.html
    return DIST / p / "index.html"


def write_page(url_path: str, html: str) -> None:
    out = page_path(url_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # url_for даёт абсолютные пути от корня; для project pages нужен префикс
    if PAGES_PREFIX:
        def _pfx(m: re.Match[str]) -> str:
            return f"{m.group(1)}{PAGES_PREFIX}/"

        html = re.sub(r'((?:href|src|action)=["\'])/(?!/)', _pfx, html)
        # srcset: "/static/a.jpg 1x, /static/b.jpg 2x"
        def _srcset(m: re.Match[str]) -> str:
            attr, body, quote = m.group(1), m.group(2), m.group(3)
            parts = []
            for chunk in body.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if chunk.startswith("/") and not chunk.startswith("//"):
                    chunk = PAGES_PREFIX + chunk
                parts.append(chunk)
            return f'{attr}{", ".join(parts)}{quote}'

        html = re.sub(
            r'(srcset=["\'])([^"\']*)(["\'])',
            _srcset,
            html,
            flags=re.IGNORECASE,
        )
    if html.startswith("\ufeff"):
        html = html.lstrip("\ufeff")
    out.write_text(html, encoding="utf-8", newline="\n")
    print(" ", url_path or "/", "→", out.relative_to(DIST))


def main() -> int:
    init_community_db()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    routes = [
        "/",
        "/product",
        "/download",
        "/changelog",
        "/changes",
        "/blog",
        "/community",
        "/about",
        "/whats-new",
        "/tips",
        "/requirements",
        "/privacy",
        "/accessibility",
        "/support",
        "/developers",
    ]
    for post in load_blog_posts():
        slug = post.get("slug")
        if slug:
            routes.append(f"/blog/{slug}")

    print(f"Freeze → {DIST} (prefix={PAGES_PREFIX})")
    client = app.test_client()
    with app.app_context():
        # Треды сообщества (снимок только для чтения)
        db = get_db()
        for (tid,) in db.execute("SELECT id FROM threads ORDER BY id").fetchall():
            routes.append(f"/community/t/{tid}")

        for route in routes:
            resp = client.get(route)
            if resp.status_code != 200:
                print(f"FAIL {route}: HTTP {resp.status_code}")
                return 1
            write_page(route, resp.get_data(as_text=True))

        # static
        static_src = ROOT / "static"
        shutil.copytree(static_src, DIST / "static")
        print("  static/ copied")

        # API каталога магазина (JSON)
        api = client.get("/api/store/catalog")
        if api.status_code == 200:
            (DIST / "api" / "store").mkdir(parents=True, exist_ok=True)
            (DIST / "api" / "store" / "catalog.json").write_bytes(api.data)
            print("  api/store/catalog.json")

    # nojekyll + 404 → home
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    home = (DIST / "index.html").read_text(encoding="utf-8")
    if home.startswith("\ufeff"):
        home = home.lstrip("\ufeff")
        (DIST / "index.html").write_text(home, encoding="utf-8")
    (DIST / "404.html").write_text(home, encoding="utf-8")

    # /gtos/favicon.ico — многие браузеры ищут именно в корне сайта
    ico = ROOT / "static" / "img" / "favicon.ico"
    if ico.is_file():
        shutil.copy2(ico, DIST / "favicon.ico")
        print("  favicon.ico (root)")

    print("OK", DIST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
