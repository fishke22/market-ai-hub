"""Zero-cost official event calendar refresh（公開來源，無金鑰、無 broker）。

刷新 dated official-event store，供 get_event_calendar 與 JNU 交易路徑的
事件語境使用。fail-honest：
- 每次執行都寫 data/events/refresh_log.json（成功/失敗皆可觀測）
- 部分來源失敗保留其餘結果；全部失敗 exit 1 且不動 store
- BLS 解析為空時把原始 HTML 前段 dump 成 diag 檔供日後診斷
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone

from market_ai_hub.providers.base import ProviderError
from market_ai_hub.providers.event_calendar import DIAG, LAST_SOURCE_STATUS, collect_events
from market_ai_hub.targets.events import EventStore


def main() -> int:
    store = EventStore()
    log_path = store.dir / "refresh_log.json"
    entry: dict = {"ok": False, "stored": 0,
                   "generated_at": datetime.now(timezone.utc).isoformat()}
    try:
        events = collect_events()
        entry["collected"] = len(events)
        by_source: dict[str, int] = {}
        for e in events:
            src = e.source or ""
            by_source[src] = by_source.get(src, 0) + 1
        stored = 0
        for src in by_source:
            stored += store.replace_scheduled_for(
                src, [e for e in events if (e.source or "") == src]
            )
        entry["ok"] = True
        entry["sources"] = by_source
        entry["source_status"] = dict(LAST_SOURCE_STATUS)   # REFRESHED vs BLOCKED_OR_FAILED
        entry["stored"] = stored
        entry["upcoming_top5"] = [e.event_name for e in store.upcoming(top_n=5)]
        code = 0
    except ProviderError as exc:
        entry["error"] = str(exc)
        code = 1
    except Exception as exc:  # 非預期錯誤：完整保留真相，不吞
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["traceback"] = traceback.format_exc()
        code = 1
    if DIAG:
        dumped: list[str] = []
        for name, text in DIAG.items():
            target = store.dir / f"diag_{name.replace(' ', '_').replace('/', '_').lower()}.html"
            try:
                target.write_text(text, encoding="utf-8")
                dumped.append(target.name)
            except OSError:
                pass
        entry["diag_dumped"] = dumped
    try:
        log_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps(entry, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())