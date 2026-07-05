"""主入口：拉取行情、判断交易时段、推送通知。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time
from pathlib import Path

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


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def is_cn_trading(dt: datetime) -> bool:
    if not is_weekday(dt):
        return False
    t = dt.time()
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon


def is_hk_trading(dt: datetime) -> bool:
    if not is_weekday(dt):
        return False
    t = dt.time()
    morning = time(9, 30) <= t <= time(12, 0)
    afternoon = time(13, 0) <= t <= time(16, 0)
    return morning or afternoon


def is_us_trading(dt: datetime) -> bool:
    if not is_weekday(dt):
        return False
    t = dt.time()
    evening = time(21, 30) <= t <= time(23, 59, 59)
    early = time(0, 0) <= t <= time(4, 0)
    return evening or early


def _collect_markets(items: list[dict]) -> set[str]:
    markets: set[str] = set()
    for item in items:
        markets.add(item.get("market") or infer_market(item["code"]))
    return markets


def should_push(config: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    force = os.environ.get("FORCE_PUSH", "").lower() in ("1", "true", "yes")
    if force:
        return True

    markets = _collect_markets(config.get("indices", []))
    markets |= _collect_markets(config.get("stocks", []))

    if config.get("funds") and is_cn_trading(now):
        return True

    market_checks = {
        "cn": is_cn_trading,
        "hk": is_hk_trading,
        "us": is_us_trading,
    }
    for market in markets:
        checker = market_checks.get(market)
        if checker and checker(now):
            return True
    return False


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
    now = datetime.now()

    if not should_push(config, now):
        print(f"[{now:%Y-%m-%d %H:%M:%S}] 非交易时段，跳过推送。")
        return 0

    indices, funds, stocks = collect_quotes(config)
    if not indices and not funds and not stocks:
        print("未获取到任何行情数据。")
        return 1

    title, body = format_push_message(indices, funds, stocks, now)
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
