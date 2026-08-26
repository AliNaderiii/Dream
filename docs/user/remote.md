# Remote access (P9)

`dream-serve` exposes Dream on **loopback** so a phone on the same machine
(or, with `--lan`, a private RFC1918 address) can call JSON-RPC.

## Honest limits

- Default bind is `127.0.0.1:8765`. That does **not** leave the machine.
- `--lan --host 192.168.x.x` is required for LAN. `0.0.0.0` and public IPs
  are refused.
- Tokens travel as `Authorization: Bearer`. A `?token=` query is rejected.
- A **read** token can call `health` / `remotegw.status`. It cannot issue,
  rotate, revoke, or change the bind.
- The QR on the Remote page is the **URL only**. Paste the token once.

## Commands

```text
python -m dream.remotegw --help
python -m dream.remotegw --preview
dream-serve --host 127.0.0.1 --port 8765
```

Missing FastAPI is not required for this façade (stdlib HTTP). The older
`gateway_server.py` SPA still needs `pip install -e ".[web]"`.
