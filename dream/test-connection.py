#!/usr/bin/env python3
"""
Connection diagnostic for OpenAI-compatible endpoints.

Runs the same request four ways to isolate why a provider rejects it:
plain urllib, urllib with a browser User-Agent, a chat completion, and a
chat completion with tools. Prints exactly which variant works.

    python test_connection.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("DREAM_MODEL", "gpt-4o-mini")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def mask(key: str) -> str:
    return f"{key[:6]}...{key[-4:]}" if len(key) > 12 else "(empty)"


def attempt(label: str, url: str, headers: dict, body: dict | None = None) -> bool:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode()
        print(f"  [ OK ]   {label}")
        if body:
            parsed = json.loads(payload)
            msg = parsed["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if calls:
                print(f"           tool invoked: {calls[0]['function']['name']}")
            else:
                text = (msg.get("content") or "")[:70].replace("\n", " ")
                print(f"           reply: {text}")
        return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200].strip().replace("\n", " ")
        print(f"  [FAIL]   {label}")
        print(f"           HTTP {e.code}: {detail}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL]   {label}")
        print(f"           {type(e).__name__}: {e}")
        return False


def main() -> int:
    print()
    print(f"  endpoint : {BASE}")
    print(f"  model    : {MODEL}")
    print(f"  key      : {mask(KEY)}")
    print()

    if not KEY:
        print("  OPENAI_API_KEY is not set. Set it and rerun.")
        return 1

    plain = {"Authorization": f"Bearer {KEY}"}
    withua = {**plain, "User-Agent": BROWSER_UA, "Accept": "application/json"}
    postua = {**withua, "Content-Type": "application/json"}

    print("  1. list models, default urllib headers")
    a = attempt("plain", f"{BASE}/models", plain)

    print("\n  2. list models, browser User-Agent")
    b = attempt("with User-Agent", f"{BASE}/models", withua)

    print("\n  3. chat completion")
    c = attempt(
        "chat",
        f"{BASE}/chat/completions",
        postua,
        {"model": MODEL, "messages": [{"role": "user", "content": "Reply with: ok"}],
         "max_tokens": 16},
    )

    print("\n  4. chat completion with a tool")
    d = attempt(
        "tool calling",
        f"{BASE}/chat/completions",
        postua,
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": "What time is it? Use the tool."}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_datetime",
                    "description": "Return the current date and time.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
            "tool_choice": "auto",
        },
    )

    print("\n" + "  " + "-" * 56)
    if not a and b:
        print("""
  DIAGNOSIS: the endpoint rejects Python's default User-Agent.

  This is a bug in dream/agent.py, which sends no User-Agent header, so
  Cloudflare classifies the request as a bot and returns error 1010.

  Fix: add a User-Agent header to OpenAIBackend.""")
    elif not a and not b:
        print("""
  DIAGNOSIS: the endpoint is unreachable regardless of headers.

  Likely a geographic restriction or an invalid key. Check the HTTP code
  above: 401 means the key is wrong, 403 with code 1009 means the region
  is blocked, 403 with 1010 means bot detection.""")
    elif c and not d:
        print("""
  DIAGNOSIS: the model replies but does not call tools.

  Choose a model that supports tool calling.""")
    elif a and b and c and d:
        print("""
  DIAGNOSIS: everything works. The provider is usable as-is.""")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
