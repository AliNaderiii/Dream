"""Measure the real request-per-minute allowance of the configured provider.

Sends a few tiny requests and reports which succeed and which are rate
limited. Prints no secrets: the key is never shown, not even partially.

Run it in the same PowerShell window that start-telegram.ps1 uses, so it
reads exactly the same environment.
"""

import json
import os
import time
import urllib.error
import urllib.request

LINE = "-" * 58
PROBES = 6


def box(title):
    print()
    print(LINE)
    print(title)
    print(LINE)


def scrub(text, key):
    if key and len(key) >= 4:
        text = text.replace(key, "<redacted-key>")
    return text


def probe(base, key, model):
    """Send the smallest possible chat request. Return (status, detail)."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "dream-assistant/0.1.0",
        },
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            json.loads(response.read().decode("utf-8"))
        return 200, f"{time.time() - started:.1f}s"
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")[:120]
        except Exception:  # noqa: BLE001
            detail = ""
        return exc.code, scrub(detail, key)
    except Exception as exc:  # noqa: BLE001
        return 0, scrub(f"{type(exc).__name__}: {exc}", key)


def main():
    base = os.environ.get("OPENAI_BASE_URL", "").strip()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("DREAM_MODEL", "").strip()

    box("1. WHAT THIS WINDOW HAS")
    print(f"base url : {base or '(not set)'}")
    print(f"model    : {model or '(not set)'}")
    print(f"key set  : {'yes' if key else 'NO'}")
    if not (base and key and model):
        print()
        print("Missing configuration. Run this in the window where you")
        print("already ran start-telegram.ps1, or set the three variables.")
        return 2

    box(f"2. SENDING {PROBES} TINY REQUESTS, ONE PER SECOND")
    print("Each costs about one token. This is a measurement, not a chat.")
    print()
    ok = limited = other = 0
    first_limit_at = None
    for i in range(1, PROBES + 1):
        status, detail = probe(base, key, model)
        if status == 200:
            ok += 1
            print(f"  request {i}  OK        {detail}")
        elif status == 429:
            limited += 1
            if first_limit_at is None:
                first_limit_at = i
            print(f"  request {i}  429 rate limited")
        else:
            other += 1
            print(f"  request {i}  {status}  {detail}")
        if i < PROBES:
            time.sleep(1.0)

    box("3. RESULT")
    print(f"succeeded    : {ok} of {PROBES}")
    print(f"rate limited : {limited}")
    if other:
        print(f"other errors : {other}")
    print()

    if other and not ok:
        print("Requests are failing for a reason other than the quota.")
        print("Read the message above. A 401 means the key is wrong; a 404")
        print("means the model name is wrong for this provider.")
    elif ok >= 5:
        print("Your allowance is comfortable. Dream sends 2 requests per")
        print("message, so this supports normal back-and-forth chatting.")
        print()
        print("You can remove DREAM_EXTRACTION from start-telegram.ps1")
        print("and get automatic memory back.")
    elif ok >= 3:
        print("Your allowance improved but is still modest. Keep")
        print("DREAM_EXTRACTION set to off so each message costs 1 request")
        print("instead of 2, and avoid rapid-fire messages.")
    elif ok >= 1:
        print(f"Only {ok} request(s) got through before the limit.")
        print("The tier upgrade may not have applied to this model. Try a")
        print("model with a higher allowance, or wait a minute and rerun.")
    else:
        print("Every request was rate limited. Either the upgrade has not")
        print("taken effect for this model, or a previous burst is still")
        print("counted. Wait sixty seconds and run this again before")
        print("changing anything.")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
