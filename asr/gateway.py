from __future__ import annotations

import asyncio
import os
from contextlib import suppress

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


FUNASR_TARGET = os.getenv("FUNASR_TARGET", "ws://127.0.0.1:10095")
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("ASR_UPSTREAM_TIMEOUT_SECONDS", "8"))
MAX_AUDIO_CHUNK_BYTES = int(os.getenv("ASR_MAX_AUDIO_CHUNK_BYTES", "262144"))

app = FastAPI(title="Peach FunASR Gateway")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "peach-asr",
        "target": FUNASR_TARGET,
        "mode": "funasr-2pass",
        "cpu_profile": "4vcpu-8gb",
    }


@app.get("/health/deep")
async def deep_health() -> dict:
    try:
        async with websockets.connect(
            FUNASR_TARGET,
            open_timeout=UPSTREAM_TIMEOUT_SECONDS,
            ping_interval=None,
            close_timeout=1,
        ):
            upstream = "ok"
    except Exception as exc:  # pragma: no cover - depends on external FunASR runtime
        upstream = f"unavailable: {type(exc).__name__}"
    return {"status": "ok" if upstream == "ok" else "degraded", "upstream": upstream}


@app.websocket("/asr")
async def asr_proxy(client: WebSocket) -> None:
    await client.accept()
    try:
        async with websockets.connect(
            FUNASR_TARGET,
            max_size=None,
            open_timeout=UPSTREAM_TIMEOUT_SECONDS,
            ping_interval=10,
            ping_timeout=10,
            close_timeout=2,
        ) as upstream:
            await proxy_bidirectional(client, upstream)
    except Exception as exc:
        with suppress(Exception):
            await client.send_json({"error": "funasr_unavailable", "detail": str(exc)[:240]})
            await client.close(code=1011)


async def proxy_bidirectional(client: WebSocket, upstream) -> None:
    async def client_to_upstream() -> None:
        while True:
            message = await client.receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                break
            text = message.get("text")
            audio = message.get("bytes")
            if text is not None:
                await upstream.send(text)
            elif audio is not None:
                if len(audio) > MAX_AUDIO_CHUNK_BYTES:
                    raise ValueError("audio chunk too large")
                await upstream.send(audio)

    async def upstream_to_client() -> None:
        async for message in upstream:
            if isinstance(message, bytes):
                await client.send_bytes(message)
            else:
                await client.send_text(message)

    tasks = {
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    }
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    for task in pending:
        with suppress(asyncio.CancelledError):
            await task
    for task in done:
        exc = task.exception()
        if exc and not isinstance(exc, WebSocketDisconnect):
            raise exc
