.pragma library

// Raytone Models app: pure helpers (tested under node by tests/test_app_logic.py).

var GIB = 1073741824

function gib(bytes) {
    if (bytes === null || bytes === undefined) return "—"
    var g = Number(bytes) / GIB
    return (g === 0 ? "0" : g.toFixed(2)) + " GiB"
}

// Weights plus runtime and a modest KV cache, against the unified pool CPU and GPU share.
function fit(bytes, total) {
    if (!total) return "unknown"
    var needed = Number(bytes) * 1.15 + 6 * GIB
    if (needed <= 0.8 * total) return "fits"
    if (needed <= 0.95 * total) return "tight"
    return "too large"
}

// The usual 4-bit choice when it fits; otherwise the largest variant that leaves room to work.
function recommended(variants, total) {
    var fitting = (variants || []).filter(function (v) { return fit(v.size, total) === "fits" })
    var preferred = ["Q4_K_M", "UD-Q4_K_XL", "Q4_K_XL"]
    for (var i = 0; i < preferred.length; i++)
        for (var j = 0; j < fitting.length; j++)
            if (fitting[j].name === preferred[i]) return fitting[j].name
    var roomy = fitting.filter(function (v) { return v.size <= 0.6 * total && v.name !== "all files" })
    // full precision decodes far slower on a bandwidth-bound machine: only when nothing else fits
    var quantized = roomy.filter(function (v) { return !/^(BF16|F16|F32)$/.test(v.name) })
    var pool = quantized.length ? quantized : roomy
    pool.sort(function (a, b) { return b.size - a.size })
    return pool.length ? pool[0].name : ""
}

function recipeAction(r) {
    if (r.running) return "stop"
    if (r.conflicts && r.conflicts.length) return "conflict"
    return r.state === "ready" ? "apply" : "download"
}

function tokensPerSecond(prev, cur, id) {
    if (!prev || !cur || cur.time <= prev.time) return null
    function count(s) {
        var inst = (s.instances || []).filter(function (x) { return x.id === id })[0]
        return inst && inst.counters ? inst.counters.generation_tokens : null
    }
    var a = count(prev), b = count(cur)
    if (a === null || b === null || a === undefined || b === undefined || b < a) return null
    return Math.round((b - a) / (cur.time - prev.time))
}

function shortRev(rev) { return String(rev || "").slice(0, 8) }
function repoName(repo) { return String(repo).split("/").pop() }
function repoOrg(repo) { return String(repo).split("/")[0] }

function modelState(m) {
    if (m.complete === true && !m.incomplete) return "ready"
    if (m.complete === false) return "incomplete " + Math.floor(100 * Number(m.progress || 0)) + "%"
    if (m.incomplete) return "downloading"
    return "unverified"
}

// The command each connectable agent starts with (in a terminal, from the Agents page).
function agentCommand(id) {
    var commands = { "opencode": "opencode", "claude": "claude", "crush": "crush", "pi": "pi" }
    return commands[id] || null
}
