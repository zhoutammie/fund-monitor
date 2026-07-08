"""主入口：拉取行情、判断交易时段、推送通知。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from fetcher import (
    fetch_funds,
    fetch_indices,
    fetch_indices_akshare_fallback,
    infer_market,
)
from formatter import format_push_message
from notifier import dispatch_push

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "docs" / "watchlist.json"
TZ = ZoneInfo("Asia/Shanghai")
US_TZ = ZoneInfo("America/New_York")

CN_MARKETS = frozenset({"cn"})
HK_MARKETS = frozenset({"hk"})
US_MARKETS = frozenset({"us"})

# GitHub Actions 定时任务常延迟 5–30 分钟，A/H 股用较宽容差
SLOT_TOLERANCE_MIN = 20

# 美股：开盘+30min、收盘-30min，用时间窗口（避免 Actions 延迟错过）
US_OPEN_PUSH = (time(10, 0), time(10, 45))   # 美东 10:00–10:45
US_CLOSE_PUSH = (time(15, 30), time(15, 59))  # 美东 15:30–15:59


def _add_minutes(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    total %= 24 * 60
    return time(total // 60, total % 60)


def build_session_slots(
    session_open: time,
    session_close: time,
    *,
    open_offset_min: int = 5,
    close_offset_min: int = 5,
    interval_min: int = 30,
) -> list[time]:
    """从「开盘+N 分钟」到「收盘-N 分钟」，每 interval 分钟一个推送点（含首尾）。"""
    start = _add_minutes(session_open, open_offset_min)
    end = _add_minutes(session_close, -close_offset_min)
    slots = [start]
    cur = _add_minutes(start, interval_min)
    while cur < end:
        slots.append(cur)
        cur = _add_minutes(cur, interval_min)
    if slots[-1] != end:
        slots.append(end)
    return slots


def _init_push_slots() -> None:
    global CN_PUSH_SLOTS, HK_PUSH_SLOTS
    CN_PUSH_SLOTS = build_session_slots(time(9, 30), time(11, 30)) + build_session_slots(
        time(13, 0), time(15, 0)
    )
    HK_PUSH_SLOTS = build_session_slots(time(9, 30), time(12, 0)) + build_session_slots(
        time(13, 0), time(16, 0)
    )


_init_push_slots()


def now_local() -> datetime:
    """北京时间（用于消息展示）。"""
    return datetime.now(TZ).replace(tzinfo=None)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def item_market(item: dict, default: str = "cn") -> str:
    code = item.get("code", "")
    return item.get("market") or infer_market(code) or default


def filter_config_by_markets(config: dict, markets: frozenset[str]) -> dict:
    def keep(item: dict, default_market: str = "cn") -> bool:
        return item_market(item, default_market) in markets

    return {
        "indices": [i for i in config.get("indices", []) if keep(i)],
        "stocks": [i for i in config.get("stocks", []) if keep(i)],
        "funds": [f for f in config.get("funds", []) if keep(f, "cn")],
        "push": config.get("push", {}),
    }


def config_has_markets(config: dict, markets: frozenset[str]) -> bool:
    sub = filter_config_by_markets(config, markets)
    return bool(sub["indices"] or sub["stocks"] or sub["funds"])


def matches_push_slot(now: datetime, slots: list[time] | tuple[time, ...]) -> bool:
    now_min = now.hour * 60 + now.minute
    best_diff = min(abs(now_min - (slot.hour * 60 + slot.minute)) for slot in slots)
    return best_diff <= SLOT_TOLERANCE_MIN


def in_time_window(t: time, start: time, end: time) -> bool:
    return start <= t <= end


def is_us_push_time(now_us: datetime) -> bool:
    if now_us.weekday() >= 5:
        return False
    t = now_us.time()
    return in_time_window(t, *US_OPEN_PUSH) or in_time_window(t, *US_CLOSE_PUSH)


def is_cn_trading_time(t: time) -> bool:
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(15, 0))


def is_hk_trading_time(t: time) -> bool:
    return (time(9, 30) <= t <= time(12, 0)) or (time(13, 0) <= t <= time(16, 0))


def is_weekday_in_tz(tz: ZoneInfo) -> bool:
    return datetime.now(tz).weekday() < 5


def get_active_markets(config: dict) -> frozenset[str]:
    force = os.environ.get("FORCE_PUSH", "").lower() in ("1", "true", "yes")
    active: set[str] = set()

    if force:
        if config_has_markets(config, CN_MARKETS):
            active.add("cn")
        if config_has_markets(config, HK_MARKETS):
            active.add("hk")
        if config_has_markets(config, US_MARKETS):
            active.add("us")
        return frozenset(active)

    now_bj = datetime.now(TZ).replace(tzinfo=None)
    now_us = datetime.now(US_TZ).replace(tzinfo=None)

    if config_has_markets(config, CN_MARKETS) and is_weekday_in_tz(TZ):
        if is_cn_trading_time(now_bj.time()) and matches_push_slot(now_bj, CN_PUSH_SLOTS):
            active.add("cn")

    if config_has_markets(config, HK_MARKETS) and is_weekday_in_tz(TZ):
        if is_hk_trading_time(now_bj.time()) and matches_push_slot(now_bj, HK_PUSH_SLOTS):
            active.add("hk")

    if config_has_markets(config, US_MARKETS) and is_weekday_in_tz(US_TZ):
        if is_us_push_time(now_us):
            active.add("us")

    return frozenset(active)


def session_label_for(markets: frozenset[str]) -> str:
    parts: list[str] = []
    if "cn" in markets:
        parts.append("A股")
    if "hk" in markets:
        parts.append("港股")
    if "us" in markets:
        parts.append("美股")
    return " · ".join(parts)


def _fetch_tencent_quotes(items: list[dict]) -> list:
    if not items:
        return []

    codes = [item["code"] for item in items]
    names = {item["code"]: item.get("name", item["code"]) for item in items}

    quotes = []
    try:
        quotes = fetch_indices(codes, names)
    except Exception:
        quotes = []

    fetched_codes = {q.code for q in quotes}
    missing = [c for c in codes if c not in fetched_codes]
    if missing:
        quotes.extend(fetch_indices_akshare_fallback(missing, names))

    order = {c: i for i, c in enumerate(codes)}
    quotes.sort(key=lambda q: order.get(q.code, 999))
    return quotes


def collect_quotes(config: dict) -> tuple[list, list, list]:
    indices = _fetch_tencent_quotes(config.get("indices", []))
    stocks = _fetch_tencent_quotes(config.get("stocks", []))
    funds = fetch_funds(config.get("funds", [])) if config.get("funds") else []
    return indices, funds, stocks


def main() -> int:
    config = load_config()
    now = now_local()
    markets = get_active_markets(config)

    if not markets:
        bj = datetime.now(TZ)
        us = datetime.now(US_TZ)
        print(
            f"[北京 {bj:%Y-%m-%d %H:%M} / 美东 {us:%Y-%m-%d %H:%M}] "
            "当前不在推送时刻，跳过。"
        )
        return 0

    sub = filter_config_by_markets(config, markets)
    indices, funds, stocks = collect_quotes(sub)

    if not indices and not funds and not stocks:
        print("未获取到任何行情数据。")
        return 1

    session_label = session_label_for(markets)
    title, body = format_push_message(indices, funds, stocks, now, session_label=session_label)
    print(title)
    print(body)
    print("-" * 40)

    push_cfg = config.get("push", {})
    channels = push_cfg.get("channels", [])
    if not channels:
        print("未配置推送渠道，仅打印到日志。")
        return 0

    results = dispatch_push(channels, body, title, push_cfg)
    for channel, ok in results.items():
        status = "成功" if ok else "失败"
        print(f"推送 {channel}: {status}")

    if results and not any(results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
