#!/usr/bin/env python3
"""
Isolate why an Ollama chat request fails.

Sends the same request six ways, adding one element at a time, and prints the
full error body that the normal code path discards. The first failing step
names the culprit.

    python debug_ollama.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("DREAM_MODEL", "qwen2.5:3b")
URL = f"{HOST}/v1/chat/completions"

HEAD = {"Content-Type": "application/json", "Authorization": "Bearer ollama"}

ONE_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_datetime",
        "description": "Return the current date and time.",
        "parameters": {
            "type": "object",
            "properties": {"timezone_name": {"type": "string"}},
        },
    },
}]

# A tool with no parameters at all - a common source of rejection.
EMPTY_PARAMS_TOOL = [{
    "type": "function",
    "function": {
        "name": "list_notes",
        "description": "List workspace files.",
        "parameters": {"type": "object", "properties": {}},
    },
}]

PERSIAN_SYSTEM = (
    "You are Dream, a personal assistant.\n\n"
    "## Relevant memory\n"
    "- [semantic] I prefer dark coffee (today)\n"
    "- [episodic] Visited a coffee shop today (today)\n"
)

results: list[tuple[str, bool]] = []


def send(label: str, payload: dict) -> bool:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=body, headers=HEAD)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        note = f"tool: {calls[0]['function']['name']}" if calls else \
               f"text: {(msg.get('content') or '')[:45]}"
        print(f"  [ OK ]  {label}")
        print(f"          {note}")
        results.append((label, True))
        return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400].strip().replace("\n", " ")
        print(f"  [FAIL]  {label}")
        print(f"          HTTP {e.code}")
        print(f"          {detail}")
        results.append((label, False))
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  [FAIL]  {label}")
        print(f"          {type(e).__name__}: {e}")
        results.append((label, False))
        return False


def main() -> int:
    print(f"\n  host  : {HOST}")
    print(f"  model : {MODEL}\n")

    # Is the daemon reachable at all?
    try:
        with urllib.request.urlopen(f"{HOST}/api/tags", timeout=10) as r:
            tags = json.loads(r.read())
        names = [m["name"] for m in tags.get("models", [])]
        print(f"  Ollama running, {len(names)} model(s): {', '.join(names[:5])}")
        if MODEL not in names:
            print(f"\n  WARNING: '{MODEL}' is not in that list.")
            print(f"  Run: ollama pull {MODEL}\n")
    except Exception as e:  # noqa: BLE001
        print(f"  Cannot reach Ollama: {e}")
        print("  Is it running? Try: ollama list\n")
        return 1

    user = [{"role": "user", "content": "Say hello in one short sentence."}]

    print("\n  1. plain chat, no tools")
    send("plain", {"model": MODEL, "messages": user})

    print("\n  2. chat with one tool")
    send("one tool", {"model": MODEL, "messages": user, "tools": ONE_TOOL})

    print("\n  3. chat with tool_choice=auto")
    send("tool_choice", {"model": MODEL, "messages": user,
                         "tools": ONE_TOOL, "tool_choice": "auto"})

    print("\n  4. tool with empty parameters object")
    send("empty params", {"model": MODEL, "messages": user,
                          "tools": EMPTY_PARAMS_TOOL})

    print("\n  5. system prompt plus tools")
    send("system prompt", {
        "model": MODEL,
        "messages": [{"role": "system", "content": PERSIAN_SYSTEM}] + user,
        "tools": ONE_TOOL,
    })

    print("\n  6. Persian user message")
    send("persian input", {
        "model": MODEL,
        "messages": [{"role": "system", "content": PERSIAN_SYSTEM},
                     {"role": "user",
                      "content": "\u0633\u0644\u0627\u0645. "
                                 "\u0645\u0646 \u0639\u0644\u06cc "
                                 "\u0647\u0633\u062a\u0645."}],
        "tools": ONE_TOOL,
    })

    print("\n  7. assistant message with null content")
    send("null content", {
        "model": MODEL,
        "messages": user + [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "get_datetime",
                                          "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"result": "noon"}'},
        ],
        "tools": ONE_TOOL,
    })

    print("\n  " + "-" * 58)
    failed = [name for name, ok in results if not ok]
    if not failed:
        print("\n  All variants succeeded. The failure is elsewhere in the")
        print("  request the CLI builds. Send this output for analysis.\n")
    else:
        first = failed[0]
        print(f"\n  First failing variant: {first}")
        print("\n  That names the element the server rejects. Send this whole")
        print("  output; the fix follows from it directly.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
