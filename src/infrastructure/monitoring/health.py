#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health check HTTP server for content pipeline
Runs in background thread, exposes /health and /metrics endpoints
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    METRICS_ENABLED = os.getenv("ENABLE_METRICS", "0") == "1"
except ImportError:
    METRICS_ENABLED = False
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and metrics"""
    
    def log_message(self, format: str, *args) -> None:
        """Suppress default logging"""
        pass
    
    def do_GET(self) -> None:
        """Handle GET requests"""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/metrics" and METRICS_ENABLED:
            self._handle_metrics()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_health(self) -> None:
        """Handle health check endpoint"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "healthy", "service": "content-pipeline"}')
    
    def _handle_metrics(self) -> None:
        """Handle metrics endpoint"""
        if not METRICS_ENABLED or generate_latest is None:
            self.send_error(503, "Metrics not enabled")
            return
            
        try:
            metrics_output = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(metrics_output)
        except Exception as e:
            self.send_error(500, f"Metrics error: {e}")


class HealthCheckServer:
    """Background HTTP server for health checks"""
    
    def __init__(self, port: int = 8080):
        """Initialize health check server
        
        Args:
            port: HTTP port (default: 8080)
        """
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start health check server in background thread"""
        if self.thread and self.thread.is_alive():
            return
            
        self.server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    
    def stop(self) -> None:
        """Stop health check server"""
        if self.server:
            self.server.shutdown()
            self.server = None
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None


# Global server instance
_server: Optional[HealthCheckServer] = None


def start_health_check_server(port: int = 8080) -> Optional[HealthCheckServer]:
    """Start global health check server
    
    Args:
        port: HTTP port (default: 8080)
        
    Returns:
        HealthCheckServer instance or None if disabled
    """
    global _server
    
    # Only start if metrics enabled or explicitly requested
    if not METRICS_ENABLED and os.getenv("ENABLE_HEALTH_CHECK", "0") != "1":
        return None
    
    if _server is None:
        _server = HealthCheckServer(port)
        _server.start()
    
    return _server


def stop_health_check_server() -> None:
    """Stop global health check server"""
    global _server
    if _server:
        _server.stop()
        _server = None
