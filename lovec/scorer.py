"""Оценка заказа нейросетью — клиент как в Ловец-FPV (lovec/llm.py):
ChadGPT / Claude / любой OpenAI-совместимый API, выбирается в [llm] config.toml.
Обучение: последние 👍/👎 пользователя подмешиваются в промпт как примеры.
Fail-open: нет ключа или API упал — кандидат проходит по префильтру."""

from __future__ import annotations

import json

from lovec import llm
from lovec.models import Listing

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

Ответь СТРОГО одним JSON-объектом, без пояснений до и после:
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
    l = cfg.get("llm", {})
    passing = int(l.get("min_score", 6))   # fail-open: без нейросети кандидат проходит

    price = f"{listing.price} ₽" if listing.price else "не указан"
    user = (_examples(feedback, l.get("max_feedback_examples", 40))
            + f"\n\nНовый заказ [{listing.platform}]:\nЗаголовок: {listing.title}\n"
              f"Описание: {listing.description[:600]}\nБюджет: {price}")

    txt = llm.chat(SYSTEM, user, cfg, log, max_tokens=200)
    if txt is None:
        return passing, "нейросеть недоступна — прошёл по ключевым словам"
    try:
        start, end = txt.find("{"), txt.rfind("}")
        v = json.loads(txt[start:end + 1])
        return int(v.get("score", 0)), str(v.get("reason", ""))[:120]
    except Exception:
        log(f"llm: невнятный ответ ({txt[:100]!r}) — fail-open")
        return passing, "нейросеть ответила невнятно — по ключевым словам"
