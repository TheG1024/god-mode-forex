#!/usr/bin/env python3
"""health/server.py — Health check server for container orchestration."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json
import logging
from datetime import datetime

from config import CONFIG

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            health = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "service": "forex-signal-system"
            }
            self.wfile.write(json.dumps(health).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_server() -> HTTPServer:
    port = getattr(CONFIG, 'HEALTH_PORT', 8080)
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health check server started on port {port}")
    return server