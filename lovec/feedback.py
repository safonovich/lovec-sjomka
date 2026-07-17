"""Обучение: в начале каждого запуска забираем нажатия 👍/👎 через getUpdates
и складываем в data/feedback.json — эти примеры Claude видит при оценке новых заказов.
У бота НЕ должен стоять webhook (боты из BotFather по умолчанию без него)."""

from __future__ import annotations

import os
import time

import requests


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/{method}"


def collect(pending: dict, feedback: list[dict], offset: int, log) -> int:
    """Возвращает новый offset. pending и feedback правятся на месте."""
    try:
        r = requests.get(_api("getUpdates"),
                         params={"offset": offset, "timeout": 0}, timeout=25)
        updates = r.json().get("result", [])
    except Exception as e:
        log(f"feedback: getUpdates не сработал — {e}")
        return offset

    new_offset = offset
    for u in updates:
        new_offset = max(new_offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if not cq:
            continue
        data = cq.get("data", "")
        if "|" not in data:
            continue
        verdict_c, sk = data.split("|", 1)
        verdict = "good" if verdict_c == "g" else "bad"
        info = pending.get(sk, {})
        feedback.append({
            "key": sk, "verdict": verdict, "ts": time.time(),
            "platform": info.get("platform"), "title": info.get("title"),
            "price": info.get("price"),
        })
        log(f"feedback: {verdict} — {info.get('title', sk)}")
        try:
            requests.post(_api("answerCallbackQuery"), json={
                "callback_query_id": cq["id"],
                "text": "Запомнил 👍" if verdict == "good" else "Запомнил 👎"},
                timeout=10)
            msg = cq.get("message") or {}
            mark = "✅ учтено: моё" if verdict == "good" else "🚫 учтено: мусор"
            requests.post(_api("editMessageReplyMarkup"), json={
                "chat_id": msg.get("chat", {}).get("id"),
                "message_id": msg.get("message_id"),
                "reply_markup": {"inline_keyboard": [[{"text": mark, "callback_data": "noop|x"}]]},
            }, timeout=10)
        except Exception:
            pass

    # держим историю в разумных пределах
    if len(feedback) > 400:
        del feedback[:len(feedback) - 400]
    return new_offset
