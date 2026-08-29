#!/usr/bin/env python3
"""
Ollama Proxy — Proxies localhost:11435 → localhost:11434, logs all requests to SQLite with token counts.

Usage: python3 ollama_proxy.py serve
"""

import asyncio
import json
import sqlite3
import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from aiohttp import web


PROXY_PORT = 11435
TARGET_PORT = 11434
DB_PATH = Path.home() / ".routingmagic" / "metrics" / "ollama_usage.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ollama_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_duration INTEGER DEFAULT 0,
            request_json TEXT,
            response_json TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ou_timestamp ON ollama_usage(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ou_model ON ollama_usage(model)")
    conn.commit()
    conn.close()


def log_usage(model: str, prompt_tokens: int, completion_tokens: int, total_duration: int, request_json: dict, response_json: dict):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT INTO ollama_usage (timestamp, model, prompt_tokens, completion_tokens, total_duration, request_json, response_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        model,
        prompt_tokens,
        completion_tokens,
        total_duration,
        json.dumps(request_json),
        json.dumps(response_json),
    ))
    conn.commit()
    conn.close()


async def proxy_handler(request: web.Request) -> web.Response:
    target_url = f"http://localhost:{TARGET_PORT}{request.path_qs}"

    # Read request body
    try:
        request_data = await request.json()
    except Exception:
        request_data = {}

    model = request_data.get("model", "unknown")

    # Forward request to real Ollama
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            json=request_data if request.can_read_body else None,
        ) as resp:
            response_data = await resp.json()
            response_headers = dict(resp.headers)

    duration_ms = int((time.time() - start_time) * 1000)

    # Extract tokens from response
    prompt_tokens = response_data.get("prompt_eval_count", 0)
    completion_tokens = response_data.get("eval_count", 0)

    # Log to DB
    log_usage(model, prompt_tokens, completion_tokens, duration_ms, request_data, response_data)

    return web.json_response(response_data, headers=response_headers)


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "proxy": "ollama-proxy"})


async def stats_handler(request: web.Request) -> web.Response:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT model, COUNT(*) as requests, SUM(prompt_tokens) as prompt_tokens,
               SUM(completion_tokens) as completion_tokens
        FROM ollama_usage
        WHERE timestamp >= datetime('now', '-24 hours')
        GROUP BY model
    """).fetchall()
    conn.close()
    return web.json_response({"models": [dict(r) for r in rows]})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/stats", stats_handler)
    app.router.add_route("*", "/{tail:.*}", proxy_handler)
    return app


async def serve():
    init_db()
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", PROXY_PORT)
    await site.start()
    print(f"Ollama proxy running on http://localhost:{PROXY_PORT} → http://localhost:{TARGET_PORT}")
    print(f"Logging to {DB_PATH}")
    print("Press Ctrl+C to stop")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "serve":
        print("Usage: python3 ollama_proxy.py serve")
        sys.exit(1)

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()