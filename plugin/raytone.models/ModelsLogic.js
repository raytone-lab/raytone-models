.pragma library

// Pure helpers for Models.qml (tested under node by tests/test_panel_logic.py).

// Until recipes carry each model's parameters, "Run" uses conservative vLLM settings, and the
// tool/reasoning parsers only where the model family is known.
function runArgv(repo) {
    var name = String(repo).split("/").pop().toLowerCase().replace(/[^a-z0-9.:_-]+/g, "-")
    var argv = ["raytone-models", "start", repo, "--engine", "vllm", "--name", name,
                "--arg", "gpu-memory-utilization=0.6", "--arg", "max-model-len=65536",
                "--arg", "enable-prefix-caching", "--json"]
    if (/qwen3\.?8/i.test(repo))
        argv = argv.concat(["--arg", "enable-auto-tool-choice", "--arg", "tool-call-parser=qwen3_coder",
                            "--arg", "reasoning-parser=qwen3"])
    return argv
}

function gib(bytes) {
    var g = Number(bytes || 0) / 1073741824
    return (g === 0 ? "0" : g.toFixed(1)) + " GiB"
}

function modelState(m) {
    if (m.complete === false) return "downloading " + Math.floor(100 * Number(m.progress || 0)) + "%"
    if (m.incomplete > 0) return "downloading"
    if (m.missing && m.missing.length) return "incomplete"
    return "ready"
}

function runnable(m) {
    return (m.format === "safetensors") && modelState(m) === "ready"
}
