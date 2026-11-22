import os
import logging
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nim-proxy")

NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NIM_API_KEY = os.getenv("NIM_API_KEY", "").strip()
APP_NAME = "nim-to-openai-proxy"

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    app.state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=30.0),
        follow_redirects=True,
    )
    logger.info("Proxying to %s", NIM_BASE_URL)
    if not NIM_API_KEY:
        logger.warning("NIM_API_KEY is not set. Requests must include Authorization header.")
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(title=APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": APP_NAME,
        "target": NIM_BASE_URL,
        "api_key_configured": bool(NIM_API_KEY),
        "endpoints": ["/v1/chat/completions", "/v1/models", "/health"],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


def build_upstream_url(path: str) -> str:
    # Normalize: accept /v1/... or /... and map to NIM_BASE_URL (which includes /v1)
    clean = path.lstrip("/")
    if clean.startswith("v1/"):
        clean = clean[3:]
    elif clean == "v1":
        clean = ""
    if clean:
        return f"{NIM_BASE_URL}/{clean}"
    return NIM_BASE_URL


def forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lk = key.lower()
        if lk in HOP_BY_HOP_HEADERS:
            continue
        if lk == "authorization":
            # Pass through client-provided key; fallback handled below
            headers[key] = value
            continue
        headers[key] = value

    if "authorization" not in {k.lower() for k in headers} and NIM_API_KEY:
        headers["Authorization"] = f"Bearer {NIM_API_KEY}"

    headers["Accept-Encoding"] = "identity"
    return headers


async def proxy_request(request: Request, path: str):
    if not NIM_API_KEY and "authorization" not in {k.lower() for k in request.headers}:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "NIM_API_KEY is not configured on the server and no Authorization header was provided.",
                    "type": "authentication_error",
                }
            },
        )

    upstream_url = build_upstream_url(path)
    headers = forward_headers(request)
    body = await request.body()
    client: httpx.AsyncClient = request.app.state.client

    req = client.build_request(
        method=request.method,
        url=upstream_url,
        headers=headers,
        content=body if body else None,
        params=request.query_params,
    )

    try:
        upstream_resp = await client.send(req, stream=True)
    except httpx.RequestError as exc:
        logger.exception("Upstream request failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"Upstream request failed: {exc}", "type": "proxy_error"}},
        )

    response_headers = {
        k: v
        for k, v in upstream_resp.headers.items()
        if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() != "content-encoding"
    }

    content_type = upstream_resp.headers.get("content-type", "")
    is_stream = "text/event-stream" in content_type

    if is_stream:
        async def stream_generator():
            try:
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk
            finally:
                await upstream_resp.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=upstream_resp.status_code,
            headers=response_headers,
            media_type=content_type or "text/event-stream",
        )

    try:
        content = await upstream_resp.aread()
    finally:
        await upstream_resp.aclose()

    return Response(
        content=content,
        status_code=upstream_resp.status_code,
        headers=response_headers,
        media_type=content_type or None,
    )


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_v1(request: Request, path: str):
    return await proxy_request(request, f"v1/{path}")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_root(request: Request, path: str):
    # Avoid catching docs/openapi if ever added; keep simple for now
    if path in {"", "health"}:
        return JSONResponse(status_code=404, content={"error": {"message": "Not found"}})
    return await proxy_request(request, path)
