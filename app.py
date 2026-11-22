import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

load_dotenv()


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


OPENAI_BASE_URL = _normalize_base_url(
    os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "").strip()
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "120"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    timeout = httpx.Timeout(UPSTREAM_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.client = client
        yield


app = FastAPI(
    title="NIM to OpenAI Router",
    description="Simple router that accepts NVIDIA NIM-style chat completion requests and forwards them to an OpenAI-compatible upstream.",
    version="0.1.0",
    lifespan=lifespan,
)


def _check_inbound_auth(authorization: str | None) -> None:
    if not INBOUND_API_KEY:
        return
    expected = f"Bearer {INBOUND_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid inbound API key")


def _build_upstream_headers(authorization: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    elif authorization:
        headers["Authorization"] = authorization
    return headers


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    if payload.get("stream"):
        raise HTTPException(
            status_code=400,
            detail="stream=true is not supported by this router; use non-streaming chat completions",
        )

    # NVIDIA NIM chat completion requests are largely OpenAI-compatible.
    # Keep the payload permissive and pass through known fields unchanged.
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _check_inbound_auth(authorization)

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    payload = _normalize_payload(payload)

    if "model" not in payload or "messages" not in payload:
        raise HTTPException(
            status_code=400, detail="Fields 'model' and 'messages' are required"
        )

    upstream_url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = _build_upstream_headers(authorization)

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream_response = await client.post(
            upstream_url, json=payload, headers=headers
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream request failed: {exc.__class__.__name__}",
        ) from exc

    content_type = upstream_response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return JSONResponse(
                content=upstream_response.json(),
                status_code=upstream_response.status_code,
            )
        except ValueError:
            pass

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=content_type or "application/octet-stream",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
