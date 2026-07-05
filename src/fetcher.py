"""数据采集：腾讯财经（指数/股票）+ 天天基金（场外基金估值）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
FUND_GZ_URL = "http://fundgz.1234567.com.cn/js/{code}.js"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.qq.com/",
}


def infer_market(code: str) -> str:
    """根据代码前缀推断市场。"""
    c = code.lower()
    if c.startswith(("sh", "sz")):
        return "cn"
    if c.startswith("hk"):
        return "hk"
    if c.startswith("us"):
        return "us"
    return "cn"


@dataclass
class IndexQuote:
    code: str
    name: str
    price: float | None
    change_pct: float | None
    update_time: str | None
    source: str = "tencent"


@dataclass
class FundQuote:
    code: str
    name: str
    nav: float | None
    estimated_nav: float | None
    change_pct: float | None
    update_time: str | None
    source: str = "tiantian"


def _parse_tencent_line(line: str) -> dict[str, Any] | None:
    match = re.match(r'v_(?P<code>[a-zA-Z0-9]+)="(?P<body>.*)";?', line.strip())
    if not match or not match.group("body"):
        return None

    code = match.group("code")
    parts = match.group("body").split("~")
    if len(parts) < 6:
        return None

    name = parts[1] or code
    price = _safe_float(parts[3])
    prev_close = _safe_float(parts[4])
    change_pct = None
    if price is not None and prev_close and prev_close != 0:
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    update_time = parts[30] if len(parts) > 30 and parts[30] else None

    return {
        "code": code,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "update_time": update_time,
    }


def _safe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_indices(codes: list[str], names: dict[str, str] | None = None) -> list[IndexQuote]:
    if not codes:
        return []

    names = names or {}
    url = TENCENT_QUOTE_URL + ",".join(codes)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "gbk"

    results: list[IndexQuote] = []
    for line in resp.text.strip().split(";"):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_tencent_line(line)
        if not parsed:
            continue
        code = parsed["code"]
        results.append(
            IndexQuote(
                code=code,
                name=names.get(code, parsed["name"]),
                price=parsed["price"],
                change_pct=parsed["change_pct"],
                update_time=parsed["update_time"],
            )
        )
    return results


def fetch_fund(code: str, name: str | None = None) -> FundQuote | None:
    url = FUND_GZ_URL.format(code=code)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    match = re.search(r"jsonpgz\((\{.*\})\)", resp.text)
    if not match:
        return None

    data = json.loads(match.group(1))
    estimated_nav = _safe_float(data.get("gsz"))
    nav = _safe_float(data.get("dwjz"))
    change_pct = _safe_float(data.get("gszzl"))

    return FundQuote(
        code=code,
        name=name or data.get("name", code),
        nav=nav,
        estimated_nav=estimated_nav,
        change_pct=change_pct,
        update_time=data.get("gztime"),
    )


def fetch_funds(items: list[dict[str, str]]) -> list[FundQuote]:
    results: list[FundQuote] = []
    for item in items:
        code = str(item["code"])
        name = item.get("name", code)
        try:
            quote = fetch_fund(code, name)
            if quote:
                results.append(quote)
        except requests.RequestException:
            results.append(
                FundQuote(
                    code=code,
                    name=name,
                    nav=None,
                    estimated_nav=None,
                    change_pct=None,
                    update_time=None,
                )
            )
    return results


def fetch_indices_akshare_fallback(codes: list[str], names: dict[str, str]) -> list[IndexQuote]:
    try:
        import akshare as ak
    except ImportError:
        return []

    results: list[IndexQuote] = []
    try:
        cn_df = ak.stock_zh_index_spot_em()
        for code in codes:
            if code.startswith(("sh", "sz")):
                idx_code = code[2:]
                row = cn_df[cn_df["代码"] == idx_code]
                if row.empty:
                    continue
                r = row.iloc[0]
                results.append(
                    IndexQuote(
                        code=code,
                        name=names.get(code, r["名称"]),
                        price=_safe_float(str(r["最新价"])),
                        change_pct=_safe_float(str(r["涨跌幅"])),
                        update_time=None,
                        source="akshare",
                    )
                )
    except Exception:
        pass

    hk_codes = [c for c in codes if c.startswith("hk")]
    if hk_codes:
        try:
            hk_df = ak.stock_hk_index_spot_em()
            name_lookup = {"HSTECH": "恒生科技", "HSI": "恒生指数"}
            for code in hk_codes:
                suffix = code[2:].upper()
                row = hk_df[hk_df["代码"].astype(str).str.contains(suffix, na=False)]
                if row.empty:
                    row = hk_df[hk_df["名称"].str.contains(name_lookup.get(suffix, suffix), na=False)]
                if row.empty:
                    continue
                r = row.iloc[0]
                results.append(
                    IndexQuote(
                        code=code,
                        name=names.get(code, r["名称"]),
                        price=_safe_float(str(r["最新价"])),
                        change_pct=_safe_float(str(r["涨跌幅"])),
                        update_time=None,
                        source="akshare",
                    )
                )
        except Exception:
            pass

    us_codes = [c for c in codes if c.startswith("us")]
    if us_codes:
        try:
            global_df = ak.index_global_spot_em()
            name_lookup = {"NDX": "纳斯达克100", "SPX": "标普500"}
            for code in us_codes:
                suffix = code[2:].upper()
                keyword = name_lookup.get(suffix, suffix)
                row = global_df[global_df["名称"].str.contains(keyword, na=False)]
                if row.empty:
                    continue
                r = row.iloc[0]
                results.append(
                    IndexQuote(
                        code=code,
                        name=names.get(code, r["名称"]),
                        price=_safe_float(str(r["最新价"])),
                        change_pct=_safe_float(str(r["涨跌幅"])),
                        update_time=None,
                        source="akshare",
                    )
                )
        except Exception:
            pass

    return results
