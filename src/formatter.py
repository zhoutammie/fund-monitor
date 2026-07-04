"""消息格式化。"""

from __future__ import annotations

from datetime import datetime

from fetcher import FundQuote, IndexQuote


def _format_change(change_pct: float | None) -> str:
    if change_pct is None:
        return "—"
    sign = "+" if change_pct >= 0 else ""
    return f"{sign}{change_pct:.2f}%"


def _format_price(price: float | None) -> str:
    if price is None:
        return "—"
    if price >= 1000:
        return f"{price:,.2f}"
    return f"{price:.4f}" if price < 10 else f"{price:.2f}"


def format_push_message(
    indices: list[IndexQuote],
    funds: list[FundQuote],
    now: datetime | None = None,
) -> tuple[str, str]:
    """生成推送标题与正文。"""
    now = now or datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    title = f"📊 基金/指数监控 {now.strftime('%H:%M')}"

    lines = [f"更新时间：{time_str}", ""]

    if indices:
        lines.append("【指数】")
        for q in indices:
            lines.append(
                f"{q.name}  {_format_price(q.price)}  {_format_change(q.change_pct)}"
            )
        lines.append("")

    if funds:
        lines.append("【基金估值】")
        for q in funds:
            price = q.estimated_nav if q.estimated_nav is not None else q.nav
            lines.append(
                f"{q.name}  {_format_price(price)}  {_format_change(q.change_pct)}"
            )
        if any(q.update_time for q in funds):
            lines.append("")
            lines.append("注：场外基金为盘中估值，仅供参考。")

    body = "\n".join(lines).strip()
    return title, body
