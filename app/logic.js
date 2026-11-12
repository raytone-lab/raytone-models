.pragma library

function chatSelectionIndex(ready, selected) {
    for (var i = 0; i < ready.length; i++) {
        if (selected ? ready[i].served_name === selected : ready[i].current === true) return i
    }
    return -1
}

// Raytone Models app: pure helpers (tested under node by tests/test_app_logic.py).

var GIB = 1073741824

function gib(bytes) {
    if (bytes === null || bytes === undefined) return "—"
    var g = Number(bytes) / GIB
    return (g === 0 ? "0" : g.toFixed(2)) + " GiB"
}

function meterRatio(value) {
    return Number.isFinite(value) && value >= 0 ? Math.min(1, value) : null
}

function meterPercent(value) {
    var ratio = meterRatio(value)
    if (ratio === null) return "—"
    if (ratio > 0 && ratio < 0.01) return "<1%"
    return (ratio === 1 ? 100 : Math.min(99, Math.round(100 * ratio))) + "%"
}

function meterAmount(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return "—"
    var amount = bytes / GIB
    if (amount >= 1024) return (amount / 1024).toFixed(1) + " TiB"
    if (amount > 0 && amount < 0.05) return "<0.1 GiB"
    return amount.toFixed(1) + " GiB"
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
    if (!prev || !cur || !Number.isFinite(prev.time) || !Number.isFinite(cur.time) || cur.time <= prev.time) return null
    function count(s) {
        var inst = (s.instances || []).filter(function (x) { return x.id === id })[0]
        return inst && inst.counters ? inst.counters.generation_tokens : null
    }
    var a = count(prev), b = count(cur)
    if (!Number.isFinite(a) || !Number.isFinite(b) || a < 0 || b < a) return null
    var rate = Math.round((b - a) / (cur.time - prev.time))
    return Number.isFinite(rate) ? rate : null
}

function shortRev(rev) { return String(rev || "").slice(0, 8) }
function repoName(repo) { return String(repo).split("/").pop() }
function repoOrg(repo) { return String(repo).split("/")[0] }

// What to show a person. A repo id is not a display name and cannot be turned into one by rule:
// a name with no capital in it is just as likely to be the publisher's deliberate styling
// (openai/gpt-oss-20b is lowercase, BAAI/bge-m3 is written BGE-M3) as it is to be un-styled, and
// guessing invents a name the model is not known by. Comfy-Org/z_image_turbo read like a filename
// next to sixteen properly cased rows, so it gets an entry here. Anything not listed is shown as
// published -- that is the publisher's own casing and it is the name the model goes by.
var DISPLAY_NAMES = {
    "z_image_turbo": "Z-Image-Turbo"
}

function modelName(repo) {
    var n = repoName(repo)
    // hasOwnProperty off the prototype: a repo basename of "constructor" would otherwise find a
    // function on the object and show it as the model's name
    return Object.prototype.hasOwnProperty.call(DISPLAY_NAMES, n) ? DISPLAY_NAMES[n] : n
}

// The served name an instance gets: a slug, so lowercase throughout, and one separator -- an
// underscore in the repo id would otherwise serve the same model under two different names
// depending on whether it was started here or by a recipe (the Studio trio says "z-image-turbo").
// One pass, so a run of separators collapses to one rather than becoming a run of dashes, and the
// edges are trimmed: a leading dash would fail spec.py's NAME_RE, which wants a letter or digit.
function servedName(repo) {
    return repoName(repo).toLowerCase()
        .replace(/[^a-z0-9.:-]+/g, "-")
        .replace(/-{2,}/g, "-")
        .replace(/^-+|-+$/g, "")
}


function modelState(m) {
    if (m.complete === true) return "ready"
    // a variant download: what was asked for is what counts, not the revision's full manifest
    if (m.download && m.download.state === "running")
        return "downloading " + Math.floor(100 * Number(m.download.progress || 0)) + "%"
    if (m.download && m.download.state === "done" && (!m.incomplete || m.download.recipe)) return "ready"
    if (m.complete === false) return "incomplete " + Math.floor(100 * Number(m.progress || 0)) + "%"
    if (m.incomplete) return "downloading"
    return "unverified"
}

// This exact H3 snapshot is the one the bundled video workflow consumes.
// Other diffusion downloads still need their own engine/workflow parameters.
function minimaxStartArgs(m) {
    if (!m || m.repo !== "Comfy-Org/MiniMax-H3"
            || m.revision !== "bf92c4091e333e69b8ca1998e0a669f15cb0832b"
            || modelState(m) !== "ready") return null
    var needed = ["diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "vae/minimax_h3_video_vae_fp16.safetensors", "vae/minimax_h3_audio_vae_fp32.safetensors",
        "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"]
    if (!needed.every(function(path) { return (m.files || []).indexOf(path) >= 0 })) return null
    return ["start", m.repo + "@" + m.revision, "--engine", "comfyui",
            "--name", "minimax-h3", "--role", "video", "--arg", "disable-smart-memory", "--json"]
}

function minimaxInstance(instances) {
    return (instances || []).filter(function(i) { return i.served_name === "minimax-h3" && i.role === "video" })[0] || null
}

// What omarchy-launch-tui gets for an agent: its command, or for an agent that reads its endpoint
// from the environment, raytone-models starting it with the variables connect wrote.
function launchArgs(id) {
    if (id === "claude") return ["raytone-models", "agent-exec", "claude"]
    if (id === "copilot") return ["--app-id=org.omarchy.copilot", "raytone-models", "agent-exec", "copilot"]
    if (id === "openclaw") return ["omarchy-launch-openclaw", "--tui"]
    // Pi and Oh My Pi keep a saved default model (maybe a cloud one): name ours
    if (id === "pi" || id === "omp") return [id, "--model", "raytone/local"]
    var c = agentCommand(id)
    return c ? [c] : null
}

// The command each connectable agent starts with (in a terminal, from the Agents page).
function agentCommand(id) {
    var commands = { "opencode": "opencode", "claude": "claude", "crush": "crush", "pi": "pi", "omp": "omp", "codex": "codex", "hermes": "hermes", "copilot": "copilot" }
    return commands[id] || null
}

// Elapsed time as m:ss (video generation takes minutes).
function clock(seconds) {
    var s = Math.floor(Number(seconds) || 0)
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
}

// Instances an agent or the Chat page can talk to: ready, and not a video engine.
function chatModels(instances) {
    return (instances || []).filter(function (i) { return i.ready && i.chat !== false })
}

// The GGUF files llama.cpp runs for a model: the main file (a split model's first part) and the
// vision projector if there is one; the downloaded variant first, else the usual 4-bit one.
// Include patterns match as the downloader's do: fnmatch, * crosses directories, "dir/" is all below.
function includeMatch(path, pattern) {
    var p = /\/$/.test(pattern) ? pattern + "*" : pattern
    // A port of Python's fnmatch.translate (the downloader's rule), with "]" escaped in sets for JS
    var esc = function (t) { return t.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&") }
    var re = "", i = 0, n = p.length
    while (i < n) {
        var c = p[i++]
        if (c === "*") { re += "[\\s\\S]*"; continue }
        if (c === "?") { re += "[\\s\\S]"; continue }
        if (c !== "[") { re += esc(c); continue }
        var j = i
        if (j < n && p[j] === "!") j++
        if (j < n && p[j] === "]") j++
        while (j < n && p[j] !== "]") j++
        if (j >= n) { re += "\\["; continue }
        var stuff
        if (p.slice(i, j).indexOf("-") < 0) {
            stuff = p.slice(i, j).replace(/\\/g, "\\\\")
        } else {
            var chunks = [], k = p[i] === "!" ? i + 2 : i + 1
            while (true) {
                k = p.indexOf("-", k)
                if (k < 0 || k >= j) break
                chunks.push(p.slice(i, k))
                i = k + 1
                k = k + 3
            }
            var chunk = p.slice(i, j)
            if (chunk) chunks.push(chunk)
            else chunks[chunks.length - 1] += "-"
            for (var m = chunks.length - 1; m > 0; m--) {      // drop empty (reversed) ranges
                if (chunks[m - 1][chunks[m - 1].length - 1] > chunks[m][0]) {
                    chunks[m - 1] = chunks[m - 1].slice(0, -1) + chunks[m].slice(1)
                    chunks.splice(m, 1)
                }
            }
            stuff = chunks.map(function (t) { return t.replace(/\\/g, "\\\\").replace(/-/g, "\\-") }).join("-")
        }
        stuff = stuff.replace(/([&~|])/g, "\\$1")
        i = j + 1
        if (!stuff) re += "(?!)"                     // an empty set never matches
        else if (stuff === "!") re += "[\\s\\S]"   // a negated empty set matches any character
        else {
            if (stuff[0] === "!") stuff = "^" + stuff.slice(1)
            else if (stuff[0] === "^" || stuff[0] === "[") stuff = "\\" + stuff
            re += "[" + stuff.replace(/\]/g, "\\]") + "]"
        }
    }
    // no "s" flag: QML's JavaScript engine does not have it, so any character is [\s\S]
    return new RegExp("^(?:" + re + ")$").test(path)
}

function ggufFiles(m) {
    var files = (m.files || []).filter(function (f) { return /\.gguf$/i.test(f) })
    var asked = m.download && m.download.include && m.download.include.length ? m.download.include : null
    var picked = asked ? files.filter(function (f) { return asked.some(function (p) { return includeMatch(f, p) }) }) : []
    function projectors(list) { return list.filter(function (f) { return /mmproj/i.test(f) }) }
    function models(list) {
        return list.filter(function (f) { return !/mmproj/i.test(f) && !/-0000[2-9]-of-|-000[1-9][0-9]-of-/.test(f) }).sort()
    }
    var candidates = models(picked).length ? models(picked) : models(files)
    if (!candidates.length) return null
    var preferred = candidates.filter(function (f) { return /Q4_K_M/.test(f) })[0]
    return { model: preferred || candidates[0], mmproj: projectors(picked)[0] || projectors(files)[0] || null }
}
