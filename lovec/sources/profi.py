"""Profi.ru: лента заказов специалиста (/backoffice/n.php) под куками из секрета
PROFI_COOKIES (JSON-экспорт из расширения Cookie-Editor). Куки протухают —
при разлогине бот шлёт предупреждение в Telegram (не чаще раза в сутки)."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from lovec.models import Listing

URL = "https://profi.ru/backoffice/n.php"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_EXTRACT_JS = r"""() => {
    const cnt = el => el.querySelectorAll('a[href*="n.php?o="]').length;
    const seen = new Set(); const out = [];
    for (const a of document.querySelectorAll('a[href*="n.php?o="]')) {
        const m = a.href.match(/[?&]o=(\d+)/); if (!m) continue;
        const id = m[1]; if (seen.has(id)) continue; seen.add(id);
        let card = a, n = a.parentElement;
        while (n && cnt(n) === 1) { card = n; n = n.parentElement; }
        out.push({ id, text: (card.innerText || '').replace(/\n{2,}/g, '\n').trim() });
    }
    return out;
}"""

_SAMESITE = {"lax": "Lax", "strict": "Strict", "no_restriction": "None",
             "unspecified": "Lax", None: "Lax"}


class SessionExpired(Exception):
    pass


def _cookies() -> list[dict]:
    raw = os.environ.get("PROFI_COOKIES", "").strip()
    if not raw:
        return []
    out = []
    for c in json.loads(raw):
        out.append({
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain") or ".profi.ru",
            "path": c.get("path") or "/",
            "secure": bool(c.get("secure", True)),
            "httpOnly": bool(c.get("httpOnly", False)),
            "sameSite": _SAMESITE.get(str(c.get("sameSite", "lax")).lower(), "Lax"),
        })
    return out


def _parse_price(text: str) -> Optional[int]:
    m = re.search(r"([\d][\d\s]*)\s*₽", text)
    if not m:
        return None
    try:
        return int(re.sub(r"\s", "", m.group(1)))
    except ValueError:
        return None


def _to_listing(card: dict) -> Listing:
    text = card["text"].strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return Listing(
        platform="profi",
        id=card["id"],
        title=lines[0] if lines else "(без заголовка)",
        description="\n".join(lines[1:6]),
        price=_parse_price(text),
        url=f"https://profi.ru/backoffice/n.php?o={card['id']}",
    )


def fetch(cfg: dict, log) -> list[Listing]:
    if not cfg.get("profi", {}).get("enabled"):
        return []
    cookies = _cookies()
    if not cookies:
        log("profi: секрет PROFI_COOKIES не задан — пропускаю")
        return []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="ru-RU",
                                  timezone_id="Europe/Moscow")
        try:
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            body = page.evaluate("() => document.body.innerText") or ""
            if "n.php" not in page.url or "Вход" in body[:2000] and "заказ" not in body.lower()[:2000]:
                raise SessionExpired()
            cards = page.evaluate(_EXTRACT_JS)
        except SessionExpired:
            raise
        except Exception as e:
            log(f"profi: ошибка — {e}")
            return []
        finally:
            browser.close()

    log(f"profi: получено карточек {len(cards)}")
    return [_to_listing(c) for c in cards]
