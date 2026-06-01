"""DingTalk custom robot (加签) text push."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from typing import Any


def signed_webhook_url(webhook: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def send_text(*, webhook: str, secret: str, content: str) -> dict[str, Any]:
    url = signed_webhook_url(webhook, secret)
    body = {"msgtype": "text", "text": {"content": content}}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_text_chunks(
    *,
    webhook: str,
    secret: str,
    content: str,
    max_len: int = 4500,
) -> list[dict[str, Any]]:
    """Split long text so each chunk stays under DingTalk limits."""
    text = content.strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [send_text(webhook=webhook, secret=secret, content=text)]

    results: list[dict[str, Any]] = []
    start = 0
    part = 1
    while start < len(text):
        end = min(start + max_len, len(text))
        chunk = text[start:end]
        if end < len(text):
            chunk = chunk.rstrip() + f"\n\n…(续 {part})"
        header = f"【基金日报 {part}】\n" if part > 1 else ""
        results.append(
            send_text(webhook=webhook, secret=secret, content=header + chunk)
        )
        start = end
        part += 1
    return results
