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

    # Handle chat-like requests with "messages"
    if "messages" in summary and isinstance(summary["messages"], list):
        new_messages = []
        for msg in summary["messages"]:
            if isinstance(msg, dict) and "content" in msg and isinstance(msg.get("content"), str):
                new_msg = msg.copy()
                new_msg["content"] = new_msg["content"][:100] + "..."
                new_messages.append(new_msg)
            else:
                new_messages.append(msg)
        summary["messages"] = new_messages

    # Handle completion-like requests with "prompt"
    if "prompt" in summary and isinstance(summary.get("prompt"), str):
        summary["prompt"] = summary["prompt"][:100] + "..."

    # Handle completion-like requests with "suffix"
    if "suffix" in summary and isinstance(summary.get("suffix"), str):
        summary["suffix"] = summary["suffix"][:100] + "..."

        # Handle "prediction" data which can contain large context
    if "prediction" in summary and isinstance(summary.get("prediction"), dict):
        new_prediction = summary["prediction"].copy()
        if "content" in new_prediction and isinstance(new_prediction.get("content"), str):
            new_prediction["content"] = new_prediction["content"][:100] + "..."
        summary["prediction"] = new_prediction

    # Handle "extra" data which can contain large context
    if "extra" in summary and isinstance(summary.get("extra"), dict):
        new_extra = summary["extra"].copy()
        if "context" in new_extra and isinstance(new_extra.get("context"), list):
            new_context = []
            for item in new_extra["context"]:
                if isinstance(item, str) and len(item) > 100:
                    new_context.append(item[:100] + "...")
                else:
                    new_context.append(item)
            new_extra["context"] = new_context
        summary["extra"] = new_extra
        
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
                # Handle chat-like responses
                if "message" in new_choice and isinstance(new_choice["message"], dict):
                    new_message = new_choice["message"].copy()
                    if "content" in new_message and isinstance(new_message.get("content"), str):
                        new_message["content"] = new_message["content"][:100] + "..."
                    new_choice["message"] = new_message
                
                # Handle completion-like responses
                if "text" in new_choice and isinstance(new_choice.get("text"), str):
                    new_choice["text"] = new_choice["text"][:100] + "..."

                new_choices.append(new_choice)
            else:
                new_choices.append(choice)
        summary["choices"] = new_choices

    return summary

def _reconstruct_sse_response(chunks: list[str]) -> dict:
    """
    Reconstructs a single JSON response from a list of SSE data chunks.
    Handles both 'chat.completion' (delta.content) and 'completion' (text) formats.
    """
    full_content = ""
    role = None
    finish_reason = None
    final_usage = {}
    metadata = {}
    model_type = None # 'chat' or 'completion'

    for chunk_str in chunks:
        if not chunk_str.strip():
            continue
        try:
            data = json.loads(chunk_str)
            if not isinstance(data, dict):
                ctx.log.warn(f"SSE: Parsed data is not a dictionary: {chunk_str[:100]}")
                continue

            # Update metadata with any new non-null info from the current chunk
            # This ensures we capture final metadata like 'id', 'model', 'usage'
            for k, v in data.items():
                if k != "choices":
                    metadata[k] = v
            
            # Merge usage stats, as they can appear in multiple chunks
            if "usage" in data and isinstance(data["usage"], dict):
                final_usage.update(data["usage"])

            choices = data.get("choices")
            if not choices or not isinstance(choices, list) or not choices[0]:
                continue # This chunk is likely metadata-only (e.g., final usage stats)

            choice = choices[0]

            # --- Detect model type from first chunk and extract content ---
            if model_type is None:
                if "delta" in choice:
                    model_type = "chat"
                elif "text" in choice:
                    model_type = "completion"

            if model_type == "chat":
                delta = choice.get("delta", {})
                if "role" in delta and delta["role"]:
                    role = delta["role"]
                if "content" in delta and delta["content"]:
                    full_content += delta["content"]
            elif model_type == "completion":
                if "text" in choice and choice["text"]:
                    full_content += choice["text"]
            # --- End content extraction ---

            if choice.get("finish_reason"):
                finish_reason = choice.get("finish_reason")

        except (json.JSONDecodeError, IndexError) as e:
            ctx.log.warn(f"SSE: Could not parse JSON chunk or invalid structure: {chunk_str[:100]} | Error: {e}")

    # Ensure the final merged usage object is in the metadata
    if final_usage:
        metadata["usage"] = final_usage

    # Assemble the final, consolidated response object based on detected type
    if model_type == "chat":
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
        }
    elif model_type == "completion":
        final_response = {
            **metadata,
            "object": "text_completion.aggregated",
            "choices": [
                {
                    "index": 0,
                    "text": full_content,
                    "finish_reason": finish_reason,
                }
            ],
        }
    else: # Fallback for empty or unknown streams
        final_response = {
            **metadata,
            "object": "unknown.aggregated",
            "choices": [{"index": 0, "message": {"content": ""}, "finish_reason": finish_reason}],
        }
    
    # Add usage if it was found
    if "usage" in metadata:
        final_response["usage"] = metadata["usage"]

    return final_response

def _estimate_tokens(text: str) -> int:
    """A simple heuristic to estimate token count from text length."""
    if not text:
        return 0
    # Based on the rule of thumb that 1 token is approx. 4 characters
    return round(len(text) / 4)

# -------- addon

class CopilotLogger:
    def __init__(self, on_event_callback: Optional[Callable[[dict], None]] = None):
        self.on_event = on_event_callback

    def request(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host) or flow.request.method == "GET":
            return
        # Mark request start (mitmproxy already tracks timestamp_start, we keep this as fallback)
        flow.metadata["t_req_start_meta"] = time.time()

    def responseheaders(self, flow: http.HTTPFlow):
        """Attach streaming callback for SSE so we capture every chunk without buffering."""
        if not _is_copilot_host(flow.request.host) or flow.request.method == "GET":
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
        if not _is_copilot_host(flow.request.host) or not flow.response or flow.request.method == "GET":
            return

        # Compute timings
        t_req = flow.request.timestamp_start or flow.metadata.get("t_req_start_meta")
        t_resp_start = flow.response.timestamp_start
        t_resp_end = flow.response.timestamp_end

        ttfb = _safe_float((t_resp_start - t_req) if (t_resp_start and t_req) else None)
        latency_total = _safe_float((t_resp_end - t_req) if (t_resp_end and t_req) else None)
        streaming_duration_s = _safe_float((t_resp_end - t_resp_start) if (t_resp_end and t_resp_start) else None)

        # Sizes
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

        # Calculate output speed in Tokens Per Second (t/s)
        completion_tokens = None
        prompt_tokens = None
        output_tps = None

        # Extract prompt tokens from request if available (e.g., in `extra` field)
        if req_json_full and isinstance(req_json_full.get("extra"), dict):
            extra = req_json_full["extra"]
            p_tokens = extra.get("prompt_tokens")
            s_tokens = extra.get("suffix_tokens")
            
            # For infilling models, prompt + suffix is the total input context.
            total_input = 0
            if p_tokens is not None:
                total_input += p_tokens
            if s_tokens is not None:
                total_input += s_tokens
            
            if total_input > 0:
                prompt_tokens = total_input

        if final_resp_json and isinstance(final_resp_json.get("usage"), dict):
            usage = final_resp_json["usage"]
            completion_tokens = usage.get("completion_tokens")
            # Prefer prompt_tokens from response `usage` if available
            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
        
        # If completion tokens are not in usage, estimate them from the response text
        if completion_tokens is None and final_resp_json:
            choices = final_resp_json.get("choices")
            if choices and isinstance(choices, list) and len(choices) > 0:
                choice = choices[0]
                text_content = ""
                if "text" in choice and isinstance(choice["text"], str):
                    text_content = choice["text"]
                elif "message" in choice and isinstance(choice.get("message"), dict):
                    text_content = choice["message"].get("content", "")
                
                if text_content:
                    completion_tokens = _estimate_tokens(text_content)

        if completion_tokens is not None and streaming_duration_s is not None and streaming_duration_s > 1e-9:
            output_tps = completion_tokens / streaming_duration_s

        # Decide what to save based on config
        req_json_to_save = req_json_full if SAVE_BODIES else _summarize_req_json(req_json_full)
        resp_json_to_save = final_resp_json if SAVE_BODIES else _summarize_resp_json(final_resp_json)

        # --- Organically create/update a `usage` object in the response JSON ---
        if resp_json_to_save is not None:
            # Ensure a usage object exists
            if "usage" not in resp_json_to_save or not isinstance(resp_json_to_save.get("usage"), dict):
                resp_json_to_save["usage"] = {}
            
            usage_obj = resp_json_to_save["usage"]
            
            # Always ensure prompt and completion tokens are present in the final usage object.
            # Use calculated/estimated values as a fallback.
            if "prompt_tokens" not in usage_obj and prompt_tokens is not None:
                usage_obj["prompt_tokens"] = prompt_tokens
            
            # This is the key fix: insert completion_tokens if we have a value, even if the key didn't exist before.
            if "completion_tokens" not in usage_obj and completion_tokens is not None:
                usage_obj["completion_tokens"] = completion_tokens

            # Recalculate total_tokens to ensure it's consistent with the (potentially new) values.
            p_tok = usage_obj.get("prompt_tokens", 0)
            c_tok = usage_obj.get("completion_tokens", 0)
            r_tok = usage_obj.get("reasoning_tokens", 0)
            usage_obj["total_tokens"] = p_tok + c_tok + r_tok
        # --- End usage object normalization ---

        # --- Determine and inject model name if missing ---
        model = None
        # Prioritize the response model name, as it's the ground truth.
        if final_resp_json and final_resp_json.get("model"):
            model = final_resp_json.get("model")
        elif req_json_full and req_json_full.get("model"):
            model = req_json_full.get("model")
        else:
            # Try to infer from path for older completion APIs
            path_parts = flow.request.path.split('/')
            if "engines" in path_parts:
                try:
                    engine_index = path_parts.index("engines")
                    if engine_index + 1 < len(path_parts):
                        model = path_parts[engine_index + 1]
                except (ValueError, IndexError):
                    pass # model remains None
        
        if model:
            # Inject/overwrite model in the saved JSON objects to ensure consistency.
            # This ensures the ground truth model from the response is used everywhere.
            if req_json_to_save is not None:
                req_json_to_save["model"] = model
            if resp_json_to_save is not None:
                resp_json_to_save["model"] = model
        # --- End model injection ---

        # Write the summary event
        rec: dict[str, any] = {
            "ts_end": t_resp_end,
            "method": flow.request.method,
            "host": flow.request.host,
            "path": flow.request.path,
            "status": flow.response.status_code,
            "ttfb_s": ttfb,
            "latency_total_s": latency_total,
            "streaming_duration_s": streaming_duration_s,
            "req_bytes": req_bytes,
            "resp_bytes": resp_bytes,
            "output_tps": output_tps,
            "req_ct": req_ct,
            "resp_ct": resp_ct,
            "req_json": req_json_to_save,
            "resp_json": resp_json_to_save,
        }

        if SAVE_HEADERS:
            rec["req_headers"] = dict(flow.request.headers)
            rec["resp_headers"] = dict(flow.response.headers)

        # Write event to file
        try:
            with open(EVENTS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:
            ctx.log.error(f"Failed to write to log file: {e}")

        if self.on_event:
            self.on_event(rec)

        ctx.log.info(
            f"[Copilot] {flow.request.method} {flow.request.host}{flow.request.path} -> {flow.response.status_code} | "
            f"total: {latency_total or 0:.2f}s, ttfb: {ttfb or 0:.2f}s, "
            f"req: {req_bytes}b, resp: {resp_bytes}b, speed: {output_tps or 0:.2f} t/s"
        )

addons = [CopilotLogger()]