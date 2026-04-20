# Dashboard (Phase 4)

Lightweight web dashboard for the clawcoralpalace stack.

## Files
- `index.html` — Static dashboard UI (stack diagram, MemPalace stats, recall test)
- `api.py` — HTTP API server (port 8106) that proxies to the MemPalace bridge
- `coral-dash.service` — systemd user unit to run the API

## Install

```bash
# Copy dashboard to OpenClaw hub
mkdir -p ~/.openclaw/hub/46-clawcoralpalace
cp index.html api.py ~/.openclaw/hub/46-clawcoralpalace/

# Install systemd service
cp coral-dash.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now coral-dash
```

## Endpoints
- `GET /health` — `{ok: true, bridge_loaded: true}`
- `GET /status` — MemPalace totals (drawers, wings, rooms)
- `GET /recall?query=X&wing=Y` — semantic search, returns context_md

## Access
- Hub page: `http://<host>:8090/46-clawcoralpalace/`
- API: `http://<host>:8106/status` (or via hub proxy in future)

## Configuration
Set via environment variables in `coral-dash.service`:
- `CORAL_DASH_PORT` (default 8106)
- `MEMPALACE_BIN` (default `~/.venvs/mempalace/bin/mempalace`)
