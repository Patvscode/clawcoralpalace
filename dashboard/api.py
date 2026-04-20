#!/usr/bin/env python3
"""
Dashboard API for clawcoralpalace hub page.
Proxies requests to the MemPalace bridge and the clawcoralpalace task runner.
"""

import json
import os
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Make the bridge importable
CLAWCORALPALACE = "/home/pmello/DevTools/clawcoralpalace"
sys.path.insert(0, CLAWCORALPALACE)

try:
    from mempalace_bridge import recall, status as mempalace_status
except ImportError as e:
    print(f"Failed to import bridge: {e}", file=sys.stderr)
    recall = None
    mempalace_status = None

PORT = int(os.environ.get("CORAL_DASH_PORT", "8106"))


MEMPALACE_BIN = os.environ.get(
    "MEMPALACE_BIN",
    os.path.expanduser("~/.venvs/mempalace/bin/mempalace"),
)

_status_cache = {"data": None, "at": 0.0}
_STATUS_TTL = 30.0  # seconds


def get_status() -> dict:
    """Get MemPalace palace status by parsing `mempalace status` CLI output."""
    import re
    import time as _time

    now = _time.time()
    if _status_cache["data"] and (now - _status_cache["at"] < _STATUS_TTL):
        return _status_cache["data"]

    result = {
        "total_drawers": 0,
        "wings": {},
        "rooms": {},
    }

    try:
        proc = subprocess.run(
            [MEMPALACE_BIN, "status"],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "TERM": "dumb"},
        )
        text = proc.stdout
        # Strip ANSI
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)

        # Total drawers line: "MemPalace Status — 10000 drawers"
        m = re.search(r"(\d[\d,]*)\s+drawers", text)
        if m:
            result["total_drawers"] = int(m.group(1).replace(",", ""))

        # Wing/room parsing
        current_wing = None
        for line in text.splitlines():
            wm = re.match(r"\s*WING:\s+(\S+)", line)
            if wm:
                current_wing = wm.group(1)
                result["wings"][current_wing] = 0
                continue
            rm = re.match(r"\s*ROOM:\s+(\S+)\s+(\d+)\s+drawers", line)
            if rm and current_wing:
                room_name = rm.group(1)
                count = int(rm.group(2))
                result["wings"][current_wing] += count
                result["rooms"][room_name] = result["rooms"].get(room_name, 0) + count
    except Exception as e:
        result["error"] = str(e)

    _status_cache["data"] = result
    _status_cache["at"] = now
    return result


class CoralHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet
        pass

    def _json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # Strip hub prefix if present
        for prefix in ("/46-clawcoralpalace/api", "/api"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break

        if path == "/status" or path == "":
            self._json(200, get_status())
            return

        if path == "/recall":
            query = qs.get("query", [""])[0]
            wing = qs.get("wing", [None])[0]
            if not query:
                self._json(400, {"error": "query required"})
                return
            if recall is None:
                self._json(500, {"error": "bridge not available"})
                return
            try:
                ctx = recall(query, wing=wing or None)
                self._json(200, {
                    "query": query,
                    "num_results": len(ctx.results),
                    "context_md": ctx.to_context_md(),
                })
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        if path == "/health":
            self._json(200, {"ok": True, "bridge_loaded": recall is not None})
            return

        self._json(404, {"error": "not found", "path": path})


def main():
    server = HTTPServer(("0.0.0.0", PORT), CoralHandler)
    print(f"🪸 CORAL Palace dashboard API on :{PORT}")
    print(f"   Bridge loaded: {recall is not None}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
