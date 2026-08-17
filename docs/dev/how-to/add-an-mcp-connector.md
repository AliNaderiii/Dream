# How to add an MCP connector

Dream speaks Model Context Protocol through `dream/mcp/`. Servers appear under
**Settings → MCP Servers** and their tools join the agent's tool set.

## Steps

1. **Add a transport** if the server speaks a new protocol. Existing
   transports in `dream/mcp/transport.py` cover stdio, SSE, and WebSocket; a new
   one subclasses the transport interface and implements connect/send/receive.

2. **Register the client flow** in `dream/mcp/client.py` so `mcp.list_servers`
   and `mcp.list_tools` enumerate it.

3. **Expose bridge methods** in `dream/bridge/methods.py` if the connector adds
   new RPC (otherwise the existing `mcp.*` family is reused).

4. **Frontend:** the settings MCP tab (`apps/desktop/src/components/mcp/`) lists
   servers and tools; add a new *transport type* option if you added one, plus
   i18n keys.

5. **Test** the connector end-to-end against a local MCP server in
   `tests/test_acp.py` / a new `tests/test_mcp_*.py`.

## Security

MCP servers can call tools on your behalf. Keep every MCP-provided tool on the
same risk-tier system as native tools, and never import a server's code — only
speak to it over the wire.
