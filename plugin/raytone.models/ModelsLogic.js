.pragma library

// Pure helpers for Models.qml (tested under node by tests/test_panel_logic.py).

// Until recipes carry each model's parameters, "Run" uses conservative vLLM settings, and the
// tool/reasoning parsers only where the model family is known.
function runArgv(repo, revision) {
    var name = String(repo).split("/").pop().toLowerCase().replace(/[^a-z0-9.:_-]+/g, "-")
    var target = revision ? repo + "@" + revision : repo
    var argv = ["raytone-models", "start", target, "--engine", "vllm", "--name", name,
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

// Recipes: one button that does the next useful thing.
function recipeArgv(r) {
    var action = r.running ? "stop" : (r.state === "ready" ? "apply" : "fetch")
    return ["raytone-models", "recipe", action, r.id, "--json"]
}

function recipeAction(r, busy) {
    if (r.running) return busy ? "Stopping…" : "Stop"
    if (r.state === "ready") return busy ? "Starting…" : "Apply"
    return busy ? "Downloading…" : "Download"
}

function recipeDetail(r) {
    var models = (r.components || []).map(function (c) { return c.served_name }).join(" + ")
    return models + " · needs " + r.memory_gib + " GiB memory, " + r.disk_gib + " GiB disk"
}
