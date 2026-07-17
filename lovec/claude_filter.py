"""Оценка заказа через Claude API с обучением: последние 👍/👎 пользователя
подмешиваются в промпт как примеры. Fail-open: если API недоступен,
кандидат проходит с оценкой 5 и пометкой."""

from __future__ import annotations

import json
import os

import requests

from lovec.models import Listing

API = "https://api.anthropic.com/v1/messages"

SYSTEM = """Ты — фильтр заказов для видеографа/фотографа из Москвы (SAF).
Его цель: НЕСЛОЖНЫЕ съёмки с бюджетом примерно 20–50 тыс ₽.

ПОДХОДИТ: видеосъёмка (ролики, промо, товарное видео, рилсы, интервью, видеовизитки),
фотосъёмка (предметка, каталог, маркетплейсы, бизнес-портреты, фуд, интерьер),
простые одно-двухдневные съёмки одним специалистом.

НЕ ПОДХОДИТ: свадьбы; крупный продакшен с командой/сценарием на недели; чистый монтаж
без съёмки; поиск моделей; обучение; фото на документы; явный бюджет ниже 15 000 ₽;
подозрительные заказы (бартер, «за отзыв», лидогенерация).

Ниже могут быть примеры прошлых оценок пользователя (👍 = взял бы, 👎 = мусор).
Они ВАЖНЕЕ общих правил — подстраивайся под его вкус.

Ответь СТРОГО одним JSON-объектом:
{"score": 0-10, "reason": "кратко по-русски, до 12 слов"}
score >= 6 означает «показать пользователю»."""


def _examples(feedback: list[dict], limit: int) -> str:
    if not feedback:
        return ""
    rows = []
    for fb in feedback[-limit:]:
        mark = "👍" if fb["verdict"] == "good" else "👎"
        price = f", бюджет {fb['price']} ₽" if fb.get("price") else ""
        rows.append(f"{mark} [{fb.get('platform','?')}] {fb.get('title','')}{price}")
    return "Примеры оценок пользователя:\n" + "\n".join(rows)


def score(listing: Listing, cfg: dict, feedback: list[dict], log) -> tuple[int, str]:
    c = cfg.get("claude", {})
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    passing = int(c.get("min_score", 6))   # fail-open: без Claude кандидат проходит
    if not c.get("enabled") or not key:
        return passing, "без Claude (нет ключа) — по ключевым словам"

    price = f"{listing.price} ₽" if listing.price else "не указан"
    user = (_examples(feedback, c.get("max_feedback_examples", 40))
            + f"\n\nНовый заказ [{listing.platform}]:\nЗаголовок: {listing.title}\n"
              f"Описание: {listing.description[:600]}\nБюджет: {price}")
    try:
        r = requests.post(
            API,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": c.get("model", "claude-haiku-4-5"), "max_tokens": 200,
                  "system": SYSTEM,
                  "messages": [{"role": "user", "content": user}]},
            timeout=30)
        r.raise_for_status()
        txt = r.json()["content"][0]["text"]
        start, end = txt.find("{"), txt.rfind("}")
        v = json.loads(txt[start:end + 1])
        return int(v.get("score", 0)), str(v.get("reason", ""))[:120]
    except Exception as e:
        log(f"claude: ошибка ({e}) — fail-open")
        return passing, "Claude недоступен — пропущен по ключевым словам"
