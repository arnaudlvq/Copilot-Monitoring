# copilot_logger.py
import os, json, time, pathlib
from typing import Optional, Callable
from mitmproxy import http, ctx

ALLOWED_HOSTS = {
    "api.githubcopilot.com",
    "api.individual.githubcopilot.com",
    "proxy.githubcopilot.com",
    "proxy.individual.githubcopilot.com",
}

# --- Configuration ---
# Set these to True to save the full request/response bodies and headers.
# WARNING: This can create very large log files.
SAVE_BODIES = False
SAVE_HEADERS = False
# --- End Configuration ---

BASE_DIR = pathlib.Path(os.path.expanduser("~/.mitmproxy/intercepter_vscode/copilot_mitm"))
EVENTS_PATH = BASE_DIR / "events.jsonl"
BASE_DIR.mkdir(parents=True, exist_ok=True)

# -------- helpers

def _is_copilot_host(host: str) -> bool:
    return host in ALLOWED_HOSTS

def _looks_like_sse(ct: str) -> bool:
    return "text/event-stream" in (ct or "").lower()

def _decode(b: Optional[bytes]) -> str:
    if not b:
        return ""
    # Never raise—replace errors so we keep as much text as possible
    return b.decode("utf-8", errors="replace")

def _safe_float(x: Optional[float]) -> Optional[float]:
    try:
        return float(x) if x is not None else None
    except Exception:
        return None

def _safe_json(b: Optional[bytes]) -> Optional[dict]:
    if not b:
        return None
    try:
        return json.loads(b)
    except json.JSONDecodeError:
        return {"error": "invalid json", "content": _decode(b)[:1000]}

def _summarize_req_json(data: Optional[dict]) -> Optional[dict]:
    """Removes large message content from request JSON to save space."""
    if not data or not isinstance(data, dict):
        return data
    
    summary = data.copy()
    if "messages" in summary and isinstance(summary["messages"], list):
        new_messages = []
        for msg in summary["messages"]:
            if isinstance(msg, dict) and "content" in msg and isinstance(msg.get("content"), str):
                new_msg = msg.copy()
                new_msg["content"] = new_msg["content"][:200]
                new_messages.append(new_msg)
            else:
                new_messages.append(msg)
        summary["messages"] = new_messages
    
    if "prediction" in summary and isinstance(summary["prediction"], dict):
        if "content" in summary["prediction"] and isinstance(summary["prediction"].get("content"), str):
            new_prediction = summary["prediction"].copy()
            new_prediction["content"] = new_prediction["content"][:200]
            summary["prediction"] = new_prediction
        
    return summary

def _summarize_resp_json(data: Optional[dict]) -> Optional[dict]:
    """Removes large message content from response JSON to save space."""
    if not data or not isinstance(data, dict):
        return data

    summary = data.copy()
    if "choices" in summary and isinstance(summary["choices"], list):
        new_choices = []
        for choice in summary["choices"]:
            if isinstance(choice, dict):
                new_choice = choice.copy()
                if "message" in new_choice and isinstance(new_choice["message"], dict):
                    new_message = new_choice["message"].copy()
                    if "content" in new_message and isinstance(new_message.get("content"), str):
                        new_message["content"] = new_message["content"][:200]
                    new_choice["message"] = new_message
                new_choices.append(new_choice)
            else:
                new_choices.append(choice)
        summary["choices"] = new_choices

    return summary

def _summarize_resp_json(data: Optional[dict]) -> Optional[dict]:
    """Removes large message content from response JSON to save space."""
    if not data or not isinstance(data, dict):
        return data

    summary = data.copy()
    if "choices" in summary and isinstance(summary["choices"], list):
        new_choices = []
        for choice in summary["choices"]:
            if isinstance(choice, dict):
                new_choice = choice.copy()
                if "message" in new_choice and isinstance(new_choice["message"], dict):
                    # Create a new message dict without the 'content'
                    new_choice["message"] = {
                        k: v for k, v in new_choice["message"].items() if k != "content"
                    }
                new_choices.append(new_choice)
            else:
                new_choices.append(choice)  # Keep non-dict choices as is
        summary["choices"] = new_choices

    return summary

def _reconstruct_sse_response(chunks: list[str]) -> dict:
    """Reconstructs a single JSON response from a list of SSE data chunks."""
    full_content = ""
    role = None
    finish_reason = None
    usage = None
    metadata = {}

    for chunk_str in chunks:
        if not chunk_str.strip():
            continue
        try:
            data = json.loads(chunk_str)
            if not metadata: # Capture metadata from the first valid chunk
                metadata = {k: v for k, v in data.items() if k != "choices"}

            choices = data.get("choices")
            if not choices:  # Gracefully skip chunks with no choices (e.g. metadata chunks)
                continue

            choice = choices[0]
            delta = choice.get("delta", {})

            if "role" in delta and delta["role"]:
                role = delta["role"]
            if "content" in delta and delta["content"]:
                full_content += delta["content"]
            if choice.get("finish_reason"):
                finish_reason = choice.get("finish_reason")
            if data.get("usage"):
                usage = data.get("usage")

        except json.JSONDecodeError:
            ctx.log.warn(f"SSE: Could not parse JSON chunk: {chunk_str[:100]}")

    # Assemble the final, consolidated response object
    final_response = {
        **metadata,
        "object": "chat.completion.aggregated",
        "choices": [
            {
                "index": 0,
                "message": {"role": role, "content": full_content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }
    return final_response

# -------- addon

class CopilotLogger:
    def __init__(self, on_event_callback: Optional[Callable[[dict], None]] = None):
        self.on_event = on_event_callback

    def request(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host):
            return
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
            flow.metadata["sse_bytes"] = 0
            flow.metadata["sse_chunks"] = [] # Store chunks for later processing
            flow.metadata["sse_buffer"] = "" # Buffer for incomplete lines

            def on_chunk(chunk: bytes):
                # End-of-stream marker in mitmproxy is b""
                if chunk == b"":
                    # Process any remaining data in the buffer
                    if flow.metadata["sse_buffer"]:
                        line = flow.metadata["sse_buffer"]
                        if line.startswith("data: "):
                            data_part = line[len("data: "):].strip()
                            if data_part and data_part != "[DONE]":
                                flow.metadata["sse_chunks"].append(data_part)
                    return chunk

                flow.metadata["sse_bytes"] = flow.metadata.get("sse_bytes", 0) + len(chunk)
                
                # Add new data to buffer and split by newline
                data = flow.metadata["sse_buffer"] + _decode(chunk)
                lines = data.split("\n")
                
                # The last part might be incomplete, so it becomes the new buffer
                flow.metadata["sse_buffer"] = lines.pop()

                # Process all complete lines
                for line in lines:
                    line = line.strip()
                    if line.startswith("data: "):
                        data_part = line[len("data: "):].strip()
                        if data_part and data_part != "[DONE]":
                            flow.metadata["sse_chunks"].append(data_part)
                
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
        latency_total = _safe_float((t_resp_end - t_req) if (t_resp_end and t_req) else None)

        # Sizes
        req_bytes = len(flow.request.raw_content or b"")
        req_bytes = len(flow.request.raw_content or b"")
        # If we streamed SSE, raw_content may be empty—use counter
        is_sse = "sse_chunks" in flow.metadata
        if is_sse:
            resp_bytes = flow.metadata.get("sse_bytes", 0)
        else:
            resp_bytes = len(flow.response.raw_content or b"")

        req_ct = flow.request.headers.get("content-type", "")
        resp_ct = flow.response.headers.get("content-type", "")

        # Handle request and response bodies
        req_json_full = _safe_json(flow.request.raw_content) if ("application/json" in req_ct) else None
        final_resp_json = None

        if is_sse:
            # Reconstruct the single aggregated JSON for SSE
            final_resp_json = _reconstruct_sse_response(flow.metadata["sse_chunks"])
        elif "application/json" in resp_ct:
            final_resp_json = _safe_json(flow.response.raw_content)

        # Extract token usage if available
        usage = (final_resp_json or {}).get("usage") or {}

        # Decide what to save based on config
        req_json_to_save = req_json_full if SAVE_BODIES else _summarize_req_json(req_json_full)
        resp_json_to_save = final_resp_json if SAVE_BODIES else _summarize_resp_json(final_resp_json)

        # Write the summary event
        rec: dict[str, any] = {
            "ts_end": t_resp_end,
            "method": flow.request.method,
            "host": flow.request.host,
            "path": flow.request.path,
            "status": flow.response.status_code,
            "ttfb_s": ttfb,
            "latency_total_s": latency_total,
            "req_bytes": req_bytes,
            "resp_bytes": resp_bytes,
            "req_ct": req_ct,
            "resp_ct": resp_ct,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "req_json": req_json_to_save,
            "resp_json": resp_json_to_save,
        }

        if SAVE_HEADERS:
            rec["req_headers"] = dict(flow.request.headers)
            rec["resp_headers"] = dict(flow.response.headers)

        if self.on_event:
            self.on_event(rec)

        ctx.log.info(
            f"[Copilot] {flow.request.method} {flow.request.host}{flow.request.path} -> {flow.response.status_code} | "
            f"total: {latency_total or 0:.2f}s, ttfb: {ttfb or 0:.2f}s, "
            f"req: {req_bytes}b, resp: {resp_bytes}b, tokens: {usage.get('total_tokens', 'N/A')}"
        )

addons = [CopilotLogger()]