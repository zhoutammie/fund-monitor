"""主入口：拉取行情、判断交易时段、推送通知。"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time
from pathlib import Path

import yaml

from fetcher import fetch_funds, fetch_indices, fetch_indices_akshare_fallback
from formatter import format_push_message
from notifier import dispatch_push

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "watchlist.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def is_cn_trading(dt: datetime) -> bool:
    """A 股交易时段（北京时间）。"""
    if not is_weekday(dt):
        return False
    t = dt.time()
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon


def is_hk_trading(dt: datetime) -> bool:
    """港股交易时段（北京时间）。"""
    if not is_weekday(dt):
        return False
    t = dt.time()
    morning = time(9, 30) <= t <= time(12, 0)
    afternoon = time(13, 0) <= t <= time(16, 0)
    return morning or afternoon


def is_us_trading(dt: datetime) -> bool:
    """美股交易时段（北京时间，含夏令时近似）。"""
    if not is_weekday(dt):
        return False
    t = dt.time()
    # 21:30 ~ 23:59 或 00:00 ~ 04:00
    evening = time(21, 30) <= t <= time(23, 59, 59)
    early = time(0, 0) <= t <= time(4, 0)
    return evening or early


def should_push(config: dict, now: datetime | None = None) -> bool:
    """任一关注市场处于交易时段则推送；场外基金估值依赖 A 股时段。"""
    now = now or datetime.now()
    force = os.environ.get("FORCE_PUSH", "").lower() in ("1", "true", "yes")
    if force:
        return True

    indices = config.get("indices", [])
    funds = config.get("funds", [])
    markets = {item.get("market", "cn") for item in indices}

    if funds and is_cn_trading(now):
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


def collect_quotes(config: dict) -> tuple[list, list]:
    indices_cfg = config.get("indices", [])
    funds_cfg = config.get("funds", [])

    codes = [item["code"] for item in indices_cfg]
    names = {item["code"]: item.get("name", item["code"]) for item in indices_cfg}

    indices = []
    if codes:
        try:
            indices = fetch_indices(codes, names)
        except Exception:
            indices = []

        fetched_codes = {q.code for q in indices}
        missing = [c for c in codes if c not in fetched_codes]
        if missing:
            fallback = fetch_indices_akshare_fallback(missing, names)
            indices.extend(fallback)

        order = {c: i for i, c in enumerate(codes)}
        indices.sort(key=lambda q: order.get(q.code, 999))

    funds = fetch_funds(funds_cfg) if funds_cfg else []
    return indices, funds


def main() -> int:
    config = load_config()
    now = datetime.now()

    if not should_push(config, now):
        print(f"[{now:%Y-%m-%d %H:%M:%S}] 非交易时段，跳过推送。")
        return 0

    indices, funds = collect_quotes(config)
    if not indices and not funds:
        print("未获取到任何行情数据。")
        return 1

    title, body = format_push_message(indices, funds, now)
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
