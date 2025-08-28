# copilot_logger.py
import os, json, time, pathlib
from typing import Optional
from mitmproxy import http, ctx

ALLOWED_HOSTS = {
    "api.githubcopilot.com",
    "api.individual.githubcopilot.com",
    "proxy.githubcopilot.com",
    "proxy.individual.githubcopilot.com",
}

BASE_DIR = pathlib.Path(os.path.expanduser("~/.mitmproxy/intercepter_vscode/copilot_mitm"))
LOG_DIR = BASE_DIR / "bodies"
EVENTS_PATH = BASE_DIR / "events.jsonl"
BASE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# -------- helpers

def _is_copilot_host(host: str) -> bool:
    return host in ALLOWED_HOSTS

def _is_textual(ct: str) -> bool:
    ct = (ct or "").lower()
    return (
        "application/json" in ct
        or "text/" in ct
        or "application/javascript" in ct
        or "application/x-ndjson" in ct
    )

def _looks_like_sse(ct: str) -> bool:
    return "text/event-stream" in (ct or "").lower()

def _decode(b: Optional[bytes]) -> str:
    if not b:
        return ""
    # Never raise—replace errors so we keep as much text as possible
    return b.decode("utf-8", errors="replace")

def _write(path: pathlib.Path, data: str, mode: str = "a"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        f.write(data)

def _new_paths(flow: http.HTTPFlow):
    # Stable, human-friendly names: timestamp + last 8 of flow id
    t = int(time.time())
    short = flow.id[-8:]
    base = f"{t}_{short}"
    return (
        LOG_DIR / f"{base}_req.txt",
        LOG_DIR / f"{base}_resp.txt",
    )

def _safe_float(x: Optional[float]) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None

# -------- addon

class CopilotLogger:
    def request(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host):
            return

        # Allocate per-flow file paths once
        req_path, resp_path = _new_paths(flow)
        flow.metadata["req_path"] = str(req_path)
        flow.metadata["resp_path"] = str(resp_path)

        # Persist textual request body
        req_ct = flow.request.headers.get("content-type", "")
        if _is_textual(req_ct):
            _write(req_path, _decode(flow.request.raw_content))

        # Mark request start (mitmproxy already tracks timestamp_start, we keep this as fallback)
        flow.metadata["t_req_start_meta"] = time.time()

    def responseheaders(self, flow: http.HTTPFlow):
        """Attach streaming callback for SSE so we capture every chunk without buffering."""
        if not _is_copilot_host(flow.request.host):
            return
        if not flow.response:
            return

        resp_ct = flow.response.headers.get("content-type", "")
        if _looks_like_sse(resp_ct):
            resp_path = pathlib.Path(flow.metadata.get("resp_path") or _new_paths(flow)[1])
            flow.metadata["resp_path"] = str(resp_path)
            flow.metadata["sse_bytes"] = 0

            def on_chunk(chunk: bytes):
                # End-of-stream marker in mitmproxy is b""
                if chunk == b"":
                    return chunk
                txt = _decode(chunk)
                _write(resp_path, txt)
                flow.metadata["sse_bytes"] = flow.metadata.get("sse_bytes", 0) + len(chunk)
                return chunk  # pass-through unmodified

            flow.response.stream = on_chunk

    def response(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host) or not flow.response:
            return

        # Compute timings
        t_req = flow.request.timestamp_start or flow.metadata.get("t_req_start_meta")
        t_resp_start = flow.response.timestamp_start
        t_resp_end = flow.response.timestamp_end

        ttfb = _safe_float((t_resp_start - t_req) if (t_resp_start and t_req) else None)
        total = _safe_float((t_resp_end - t_req) if (t_resp_end and t_req) else None)

        # Sizes
        req_bytes = len(flow.request.raw_content or b"")
        # If we streamed SSE, raw_content may be empty—use counter
        if flow.metadata.get("sse_bytes") is not None:
            resp_bytes = flow.metadata.get("sse_bytes", 0)
        else:
            resp_bytes = len(flow.response.raw_content or b"")

        req_ct = flow.request.headers.get("content-type", "")
        resp_ct = flow.response.headers.get("content-type", "")

        # If not SSE and textual, persist full response body now
        if not _looks_like_sse(resp_ct) and _is_textual(resp_ct):
            resp_path = pathlib.Path(flow.metadata.get("resp_path") or _new_paths(flow)[1])
            flow.metadata["resp_path"] = str(resp_path)
            if flow.response.raw_content:
                _write(resp_path, _decode(flow.response.raw_content), mode="w")

        # Write the summary event
        rec = {
            "ts_end": t_resp_end,
            "method": flow.request.method,
            "host": flow.request.host,
            "path": flow.request.path,
            "status": flow.response.status_code,
            "ttfb_s": ttfb,
            "latency_total_s": total,
            "req_bytes": req_bytes,
            "resp_bytes": resp_bytes,
            "req_ct": req_ct,
            "resp_ct": resp_ct,
            "req_json_snippet": (json.dumps(_safe_json(flow.request.raw_content))[:2000] + "...") if ("application/json" in req_ct) else None,
            "resp_json_snippet": (json.dumps(_safe_json(flow.response.raw_content))[:2000] + "...") if ("application/json" in resp_ct) else None,
        }

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # Add this to your CopilotLogger.request method:
        ctx.log.info(f"Host seen: {flow.request.host}")
        ctx.log.info(f"[Copilot] {flow.request.method} {flow.request.path} "
                     f"-> {flow.response.status_code}  total={latency_total:.3f}s ttft={ttft:.3f}s")
addons = [CopilotLogger()]