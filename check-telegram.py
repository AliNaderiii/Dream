"""Diagnose why the Telegram front end cannot reach the Bot API.

Prints no secrets. The token is never shown, not even partially.
Run it in the same PowerShell window, with the same environment,
that start-telegram.ps1 uses.
"""

import ipaddress
import json
import os
import socket
import ssl
import sys
import urllib.request

HOST = "api.telegram.org"
LINE = "-" * 58


def box(title):
    print()
    print(LINE)
    print(title)
    print(LINE)


def main():
    box("1. WHAT PYTHON SEES")
    print(f"python        : {sys.version.split()[0]}")
    base = os.environ.get("TELEGRAM_API_BASE_URL", "").strip()
    print(f"api base url  : {base or '(default) https://api.telegram.org'}")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    print(f"token set     : {'yes' if token else 'NO - this is the problem'}")
    print(f"allowed user  : {os.environ.get('TELEGRAM_ALLOWED_USER', '(not set)')}")

    box("2. SYSTEM PROXY  (a dead proxy causes WinError 10061)")
    proxies = urllib.request.getproxies()
    if proxies:
        print("Windows has a proxy configured:")
        for k, v in proxies.items():
            print(f"    {k:8s} -> {v}")
        print()
        print("If a proxy client (v2ray, nekoray, hiddify) is NOT running,")
        print("every request is refused instantly. That is WinError 10061.")
    else:
        print("no system proxy  (good - traffic goes direct through the VPN)")

    box("3. DNS  (failure here is WinError 11001)")
    resolved = []
    try:
        infos = socket.getaddrinfo(HOST, 443, proto=socket.IPPROTO_TCP)
        resolved = sorted({i[4][0] for i in infos})
        for ip in resolved:
            addr = ipaddress.ip_address(ip)
            if addr.is_private:
                tag = "  <-- PRIVATE. This is a censorship block page."
            else:
                tag = "  <-- looks like a real Telegram address"
            print(f"    {HOST} -> {ip}{tag}")
    except Exception as exc:  # noqa: BLE001
        print(f"    FAILED: {type(exc).__name__}: {exc}")
        print()
        print("    DNS is not answering at all. The VPN is not connected,")
        print("    or it is mid-handshake, or its DNS server is unreachable.")

    box("4. TCP CONNECTION")
    ipv4 = [i for i in resolved if ipaddress.ip_address(i).version == 4]
    reachable = 0
    if not ipv4:
        print("    skipped, nothing resolved")
    for ip in ipv4:
        try:
            s = socket.create_connection((ip, 443), 15)
            print(f"    port 443 on {ip}  connected")
            reachable += 1
            s.close()
        except Exception as exc:  # noqa: BLE001
            print(f"    port 443 on {ip}  FAILED  {type(exc).__name__}: {exc}")
    if resolved and not ipv4:
        print("    only IPv6 addresses resolved, which most home lines cannot use")

    box("5. TLS HANDSHAKE  (reset here means SNI filtering)")
    if not resolved:
        print("    skipped, nothing resolved")
    else:
        try:
            ctx = ssl.create_default_context()
            with (
                socket.create_connection((HOST, 443), 15) as raw,
                ctx.wrap_socket(raw, server_hostname=HOST) as tls,
            ):
                print(f"    handshake ok, protocol {tls.version()}")
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED  {type(exc).__name__}: {exc}")

    box("6. REAL BOT API CALL")
    if not token:
        print("    skipped, no token in this window")
    else:
        url = f"{base or 'https://api.telegram.org'}/bot{token}/getMe"
        try:
            with urllib.request.urlopen(url, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                who = data.get("result", {}).get("username", "?")
                print(f"    SUCCESS. Telegram answered. Bot username: @{who}")
                print()
                print("    The network is fine. Start the bot again.")
            else:
                print(f"    Telegram rejected it: {data.get('description')}")
        except Exception as exc:  # noqa: BLE001
            text = f"{type(exc).__name__}: {exc}"
            if token:
                text = text.replace(token, "<redacted-token>")
            print(f"    FAILED  {text}")

    box("VERDICT")
    if not resolved:
        print("DNS is dead. Turn the VPN on and wait for it to say Connected.")
    elif any(ipaddress.ip_address(i).is_private for i in resolved):
        print("You are being served a block page. The VPN is not carrying")
        print("this traffic. Reconnect it, or change its DNS setting.")
    elif reachable == 0:
        print("DNS answers but nothing accepts a connection. The VPN is not")
        print("carrying this traffic. Reconnect it and run this again.")
    elif proxies:
        print("A system proxy is set. If its client is not running, that is")
        print("your WinError 10061. Start it, or clear the proxy setting.")
    else:
        print("DNS and routing look sane. Read section 6 above.")
    print()


if __name__ == "__main__":
    main()
