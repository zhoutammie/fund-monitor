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

CN_HK_MARKETS = frozenset({"cn", "hk"})
US_MARKETS = frozenset({"us"})


def now_local() -> datetime:
    """北京时间（用于展示与 A 股/港股交易时段判断）。"""
    return datetime.now(TZ).replace(tzinfo=None)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_cn_trading() -> bool:
    """A 股/港股关注项：按北京时间 9:30–11:30、13:00–15:00 推送。"""
    dt = datetime.now(TZ)
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon


def is_us_trading() -> bool:
    """美股关注项：按美东时间 9:30–16:00 推送（自动处理夏令时）。"""
    dt = datetime.now(US_TZ)
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return time(9, 30) <= t <= time(16, 0)


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


def get_push_groups(config: dict) -> set[str]:
    force = os.environ.get("FORCE_PUSH", "").lower() in ("1", "true", "yes")
    groups: set[str] = set()

    if force:
        if config_has_markets(config, CN_HK_MARKETS):
            groups.add("cn_hk")
        if config_has_markets(config, US_MARKETS):
            groups.add("us")
        return groups

    if config_has_markets(config, CN_HK_MARKETS) and is_cn_trading():
        groups.add("cn_hk")
    if config_has_markets(config, US_MARKETS) and is_us_trading():
        groups.add("us")
    return groups


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
    groups = get_push_groups(config)

    if not groups:
        bj = datetime.now(TZ)
        us = datetime.now(US_TZ)
        print(
            f"[北京 {bj:%Y-%m-%d %H:%M} / 美东 {us:%Y-%m-%d %H:%M}] "
            "当前无活跃交易时段，跳过推送。"
        )
        return 0

    indices: list = []
    funds: list = []
    stocks: list = []
    session_parts: list[str] = []

    if "cn_hk" in groups:
        sub = filter_config_by_markets(config, CN_HK_MARKETS)
        i, f, s = collect_quotes(sub)
        indices.extend(i)
        funds.extend(f)
        stocks.extend(s)
        session_parts.append("A股/港股")

    if "us" in groups:
        sub = filter_config_by_markets(config, US_MARKETS)
        i, f, s = collect_quotes(sub)
        indices.extend(i)
        funds.extend(f)
        stocks.extend(s)
        session_parts.append("美股")

    if not indices and not funds and not stocks:
        print("未获取到任何行情数据。")
        return 1

    session_label = " · ".join(session_parts)
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
