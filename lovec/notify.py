"""Telegram: пуш заказа с кнопками 👍/👎 (учат бота) и служебные сообщения."""

from __future__ import annotations

import hashlib
import os
import time

import requests

from lovec.models import Match

PLATFORM_ICON = {"youdo": "🟡 YouDo", "profi": "🔵 Profi"}


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/{method}"


def _chat_id() -> str:
    return os.environ["TG_CHAT_ID"]


def short_key(listing_key: str) -> str:
    return hashlib.sha1(listing_key.encode()).hexdigest()[:12]


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_match(m: Match, pending: dict, log) -> None:
    l = m.listing
    sk = short_key(l.key)
    price = f"{l.price:,} ₽".replace(",", " ") if l.price else "бюджет не указан"
    tag = " 🎯" if m.in_target_budget else (" 💰" if (l.price or 0) > 0 else "")
    text = (f"{PLATFORM_ICON.get(l.platform, l.platform)}{tag}\n"
            f"<b>{_esc(l.title)}</b>\n"
            f"💵 {price} · оценка {m.score}/10\n"
            f"<i>{_esc(m.reason)}</i>\n")
    desc = l.description.strip()
    if desc and desc != l.title:
        text += f"\n{_esc(desc[:400])}\n"
    text += f'\n<a href="{l.url}">Открыть заказ →</a>'

    kb = {"inline_keyboard": [[
        {"text": "👍 Моё", "callback_data": f"g|{sk}"},
        {"text": "👎 Мусор", "callback_data": f"b|{sk}"},
    ]]}
    try:
        r = requests.post(_api("sendMessage"), json={
            "chat_id": _chat_id(), "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True, "reply_markup": kb}, timeout=20)
        r.raise_for_status()
        pending[sk] = {"platform": l.platform, "title": l.title,
                       "price": l.price, "url": l.url, "ts": time.time()}
    except Exception as e:
        log(f"telegram: не отправилось — {e}")


def send_service(text: str, log) -> None:
    try:
        requests.post(_api("sendMessage"), json={
            "chat_id": _chat_id(), "text": text,
            "disable_web_page_preview": True}, timeout=20)
    except Exception as e:
        log(f"telegram(service): {e}")
