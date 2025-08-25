# copilot_logger.py
import json, os, re
from mitmproxy import http, ctx

ALLOWED_HOSTS = {
    "api.githubcopilot.com",
    "api.individual.githubcopilot.com",
    "proxy.githubcopilot.com",
    "proxy.individual.githubcopilot.com",
}
LOG_PATH = os.path.expanduser("~/.mitmproxy/intercepter_vscode/copilot_mitm_logs.jsonl")

def _safe_json(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None

def _is_copilot_host(host: str) -> bool:
    return host in ALLOWED_HOSTS

class CopilotLogger:
    def request(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host):
            return
        flow.metadata["t_req_start"] = flow.request.timestamp_start

    def response(self, flow: http.HTTPFlow):
        if not _is_copilot_host(flow.request.host) or not flow.response:
            return

        t_req = flow.request.timestamp_start
        t_resp_start = flow.response.timestamp_start
        t_resp_end = flow.response.timestamp_end
        latency_total = (t_resp_end - t_req) if (t_resp_end and t_req) else None
        ttft = (t_resp_start - t_req) if (t_resp_start and t_req) else None

        req_ct = flow.request.headers.get("content-type", "")
        resp_ct = flow.response.headers.get("content-type", "")

        rec = {
            "ts": t_resp_end,
            "method": flow.request.method,
            "host": flow.request.host,
            "path": flow.request.path,
            "status": flow.response.status_code,
            "latency_total_s": latency_total,
            "ttft_s": ttft,
            "req_bytes": len(flow.request.raw_content or b""),
            "resp_bytes": len(flow.response.raw_content or b""),
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
