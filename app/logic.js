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
    if (m.complete === true) return "ready"
    // a variant download: what was asked for is what counts, not the revision's full manifest
    if (m.download && m.download.state === "running")
        return "downloading " + Math.floor(100 * Number(m.download.progress || 0)) + "%"
    if (m.download && m.download.state === "done" && !m.incomplete) return "ready"
    if (m.complete === false) return "incomplete " + Math.floor(100 * Number(m.progress || 0)) + "%"
    if (m.incomplete) return "downloading"
    return "unverified"
}

// The command each connectable agent starts with (in a terminal, from the Agents page).
function agentCommand(id) {
    var commands = { "opencode": "opencode", "claude": "claude", "crush": "crush", "pi": "pi", "codex": "codex" }
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
