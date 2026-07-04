"""消息推送：飞书、PushPlus（微信）、邮件。"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


def send_feishu(webhook_url: str, content: str, title: str | None = None) -> bool:
    """发送飞书群机器人文本消息。"""
    if not webhook_url:
        return False

    text = f"{title}\n\n{content}" if title else content
    payload = {"msg_type": "text", "content": {"text": text}}
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("code", data.get("StatusCode", 0)) in (0, 200)


def send_pushplus(token: str, content: str, title: str = "基金指数监控") -> bool:
    """通过 PushPlus 推送到微信。"""
    if not token:
        return False

    resp = requests.post(
        "http://www.pushplus.plus/send",
        json={
            "token": token,
            "title": title,
            "content": content.replace("\n", "<br>"),
            "template": "html",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("code") == 200


def send_email(
    smtp_host: str,
    smtp_port: int,
    sender: str,
    password: str,
    receiver: str,
    subject: str,
    content: str,
) -> bool:
    """通过 SMTP 发送邮件。"""
    if not all([smtp_host, sender, password, receiver]):
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    html = content.replace("\n", "<br>")
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
    return True


def dispatch_push(
    channels: list[str],
    content: str,
    title: str,
    config: dict,
) -> dict[str, bool]:
    """按配置向多个渠道推送，返回各渠道发送结果。"""
    env = os.environ
    results: dict[str, bool] = {}

    if "feishu" in channels:
        webhook = env.get("FEISHU_WEBHOOK") or config.get("feishu_webhook", "")
        try:
            results["feishu"] = send_feishu(webhook, content, title)
        except requests.RequestException:
            results["feishu"] = False

    if "pushplus" in channels:
        token = env.get("PUSHPLUS_TOKEN") or config.get("pushplus_token", "")
        try:
            results["pushplus"] = send_pushplus(token, content, title)
        except requests.RequestException:
            results["pushplus"] = False

    if "email" in channels:
        email_cfg = config.get("email", {})
        try:
            results["email"] = send_email(
                smtp_host=env.get("SMTP_HOST") or email_cfg.get("smtp_host", ""),
                smtp_port=int(env.get("SMTP_PORT") or email_cfg.get("smtp_port", 465)),
                sender=env.get("SMTP_SENDER") or email_cfg.get("sender", ""),
                password=env.get("SMTP_PASSWORD") or email_cfg.get("password", ""),
                receiver=env.get("SMTP_RECEIVER") or email_cfg.get("receiver", ""),
                subject=title,
                content=content,
            )
        except (smtplib.SMTPException, OSError, ValueError):
            results["email"] = False

    return results
