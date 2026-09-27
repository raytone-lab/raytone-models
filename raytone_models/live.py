"""Live data for the app: the unified memory pool, each engine's token counters (Prometheus
/metrics, which vLLM, SGLang and llama.cpp serve), and a chat streamed through the router as JSON lines.

The app computes tokens per second from two counter samples; nothing here keeps state.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

METRIC_NAMES = {"vllm:generation_tokens_total": "generation_tokens", "vllm:prompt_tokens_total": "prompt_tokens",
                "vllm:num_requests_running": "running",
                "sglang:generation_tokens_total": "generation_tokens", "sglang:prompt_tokens_total": "prompt_tokens",
                "sglang:num_running_reqs": "running",
                "llamacpp:tokens_predicted_total": "generation_tokens", "llamacpp:prompt_tokens_total": "prompt_tokens",
                "llamacpp:requests_processing": "running"}
LINE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([0-9.eE+-]+)")


def memory(meminfo="/proc/meminfo"):
    """Bytes in the pool CPU and GPU share on the Thor, and how much is available."""
    values = {}
    for line in open(meminfo):
        k, _, rest = line.partition(":")
        values[k] = int(rest.split()[0]) * 1024
    return {"total": values["MemTotal"], "available": values["MemAvailable"]}


def counters(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            text = r.read().decode()
    except (OSError, ValueError):
        return None
    out = {}
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m and m.group(1) in METRIC_NAMES:
            key = METRIC_NAMES[m.group(1)]
            out[key] = out.get(key, 0.0) + float(m.group(3))
    return out


def _emit(obj):
    print(json.dumps(obj), flush=True)


def chat(router, request, timeout=600):
    """POST a streamed chat completion to the router; print {"delta"} lines, then {"done", "usage",
    "seconds", "first_token_seconds"} or {"error"}."""
    body = dict(request, stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(router.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Host": "127.0.0.1"})
    t0 = time.time()
    first, usage = None, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                d = json.loads(line[6:])
                usage = d.get("usage") or usage
                for c in d.get("choices", []):
                    delta = c.get("delta") or {}
                    text = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if (text or reasoning) and first is None:
                        first = time.time()
                    if reasoning:
                        _emit({"reasoning": reasoning})
                    if text:
                        _emit({"delta": text})
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read()).get("error", {}).get("message", str(e))
        except ValueError:
            message = str(e)
        _emit({"error": message})
        return 1
    except (OSError, ValueError) as e:
        _emit({"error": f"the router did not answer: {e}"})
        return 1
    end = time.time()
    _emit({"done": True, "usage": usage, "seconds": round(end - t0, 3),
           "first_token_seconds": round(first - t0, 3) if first else None})
    return 0


def read_request(stream=sys.stdin):
    return json.loads(stream.read())
