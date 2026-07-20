"""Один прогон радара (запускается GitHub Actions по расписанию):
фидбек → ленты → префильтр → Claude → Telegram → сохранить состояние."""

from __future__ import annotations

import datetime
import sys
import tomllib
import zoneinfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lovec import feedback, matcher, notify, scorer, store
from lovec.models import Match
from lovec.sources import profi, youdo

MSK = zoneinfo.ZoneInfo("Europe/Moscow")


def log(msg: str) -> None:
    print(f"[lovec] {msg}", flush=True)


def main() -> None:
    cfg = tomllib.loads(
        (Path(__file__).parent / "config.toml").read_text(encoding="utf-8"))

    now = datetime.datetime.now(MSK)
    h0, h1 = cfg["filter"].get("active_hours_msk", [8, 24])
    if not (h0 <= now.hour < h1):
        log(f"ночь ({now:%H:%M} МСК) — спим")
        return

    seen: list = store.load("seen.json", [])
    seen_set = set(seen)
    fb: list = store.load("feedback.json", [])
    pending: dict = store.prune_pending(store.load("pending.json", {}))
    tg_state: dict = store.load("tg_state.json", {"offset": 0})
    first_run = not seen_set

    # 1. Забираем 👍/👎 (обучение)
    tg_state["offset"] = feedback.collect(pending, fb, tg_state.get("offset", 0), log)

    # 2. Собираем ленты
    listings = []
    listings += youdo.fetch(cfg, log)
    try:
        listings += profi.fetch(cfg, log)
    except profi.SessionExpired:
        last_warn = tg_state.get("profi_warn_ts", 0)
        import time
        if time.time() - last_warn > 86400:
            notify.send_service(
                "⚠️ Куки Profi.ru протухли — обнови секрет PROFI_COOKIES "
                "(экспорт из Cookie-Editor, см. README).", log)
            tg_state["profi_warn_ts"] = time.time()
        log("profi: сессия истекла")

    # 3. Новые кандидаты
    fresh = [l for l in listings if l.key not in seen_set]
    for l in fresh:
        seen_set.add(l.key)
        seen.append(l.key)
    candidates = [l for l in fresh if matcher.prefilter(l, cfg)]
    log(f"новых {len(fresh)}, кандидатов после префильтра {len(candidates)}")

    if first_run:
        candidates = candidates[:cfg["filter"].get("first_run_max", 8)]
        log(f"первый запуск — шлём максимум {len(candidates)}")

    # 4. Нейросеть решает + шлём
    min_score = cfg.get("llm", {}).get("min_score", 6)
    sent = 0
    for l in candidates:
        sc, reason = scorer.score(l, cfg, fb, log)
        if sc < min_score:
            log(f"skip ({sc}/10): {l.title[:60]} — {reason}")
            continue
        notify.send_match(Match(l, sc, reason, matcher.in_target(l, cfg)), pending, log)
        sent += 1
    log(f"отправлено {sent}")

    # 5. Сохраняем состояние (workflow закоммитит data/ обратно)
    store.save("seen.json", seen[-5000:])
    store.save("feedback.json", fb)
    store.save("pending.json", pending)
    store.save("tg_state.json", tg_state)


if __name__ == "__main__":
    main()
