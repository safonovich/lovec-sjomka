"""YouDo: прогреваем сессию загрузкой ленты (Playwright, снимает антибот),
затем бьём в чистый JSON API из того же контекста."""

from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from lovec.models import Listing

API = "https://youdo.com/api/tasks/tasks/"
FEED = "https://youdo.com/tasks-all-opened-all"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _parse_budget(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"\d[\d\s]*", s)
    if not m:
        return None
    try:
        return int(re.sub(r"\s", "", m.group(0)))
    except ValueError:
        return None


def _to_listing(t: dict) -> Listing:
    budget = t.get("BudgetDescription") or ""
    return Listing(
        platform="youdo",
        id=str(t["Id"]),
        title=t.get("Name", ""),
        description=(t.get("Description") or budget or "").strip(),
        price=_parse_budget(budget),
        url="https://youdo.com" + (t.get("Url") or ""),
        raw={"offers": t.get("OffersCount"), "category": t.get("CategoryFlag")},
    )


def fetch(cfg: dict, log) -> list[Listing]:
    yd = cfg.get("youdo", {})
    if not yd.get("enabled"):
        return []
    body = {
        "q": "", "list": "all", "status": "opened",
        "radius": yd.get("radius_km", 50),
        "lat": yd.get("lat"), "lng": yd.get("lng"), "page": 1,
        "noOffers": False, "onlySbr": False, "onlyB2B": False, "onlyVacancies": False,
        "priceMin": "", "sortType": 1, "onlyVirtual": False,
        "categories": [yd.get("category", "photoshop")],
        "searchRequestId": str(uuid.uuid4()),
    }
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="ru-RU",
                                  timezone_id="Europe/Moscow")
        page = ctx.new_page()

        def warm() -> None:
            try:
                page.goto(FEED, wait_until="commit", timeout=30000)
                page.wait_for_timeout(4000)
            except Exception as e:
                log(f"youdo: прогрев не удался ({type(e).__name__}) — пробуем API напрямую")

        def post():
            return ctx.request.post(
                API, data=json.dumps(body),
                headers={"content-type": "application/json",
                         "x-requested-with": "XMLHttpRequest",
                         "referer": FEED},
                timeout=20000)

        try:
            r = post()                       # 1-я попытка: сразу в API
            txt = (r.text() or "").strip()
            if not txt.startswith("{"):
                log(f"youdo: API без прогрева не пустил (HTTP {r.status}) — греем сессию")
                warm()
                r = post()                   # 2-я попытка: после прогрева
                txt = (r.text() or "").strip()
            if not txt.startswith("{"):
                log(f"youdo: антибот не пустил (HTTP {r.status}, ответ: {txt[:120]!r})")
                return []
            items = r.json().get("ResultObject", {}).get("Items", [])
        except Exception as e:
            log(f"youdo: ошибка — {e}")
            return []
        finally:
            browser.close()

    max_off = yd.get("max_offers", 0)
    out = []
    for t in items:
        off = t.get("OffersCount")
        if max_off and off is not None and off > max_off:
            continue
        out.append(_to_listing(t))
    log(f"youdo: получено {len(items)}, после фильтра откликов {len(out)}")
    return out
