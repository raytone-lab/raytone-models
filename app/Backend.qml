import QtQuick
import Quickshell
import Quickshell.Io

// Everything the app knows comes from `raytone-models ... --json`; the app keeps no model state of
// its own. Lists refresh while the window is open; one action runs at a time.
Item {
    id: root

    property string cli: "raytone-models"
    property var recipes: []
    property var refusedRecipes: []
    property var models: []
    property var ollamaModels: []      // Ollama's own library, when its service is up
    property var instances: []
    property var agents: []
    property var downloads: []
    property var engines: []
    property var stats: null
    property var previousStats: null
    property var searchResults: []
    property var repoDetail: null
    property bool searching: false
    property bool loadingRepo: false
    property string busy: ""           // the key of the action in flight
    property string lastError: ""
    property string notice: ""
    property var fetching: ({})        // recipe id -> true while `recipe fetch` runs

    signal chatDelta(string text)
    signal chatReasoning(string text)
    signal chatDone(var summary)
    signal chatError(string message)
    signal chatEnded()                 // the chat process exited, finished or stopped
    signal videoDone(string path, real seconds)
    signal videoError(string message)
    signal videoEnded()

    function parse(text, fallback) {
        try { return JSON.parse(String(text || "")) } catch (e) { return fallback }
    }

    function refresh() {
        if (!recipesProc.running) recipesProc.running = true
        if (!modelsProc.running) modelsProc.running = true
        if (!ollamaProc.running) ollamaProc.running = true
        if (!instancesProc.running) instancesProc.running = true
        if (!agentsProc.running) agentsProc.running = true
        if (!downloadsProc.running) downloadsProc.running = true
        if (!enginesProc.running) enginesProc.running = true
    }

    // One action at a time; the key names it for the button that started it.
    function act(key, args, doneNotice) {
        if (actionProc.running) return
        busy = key
        lastError = ""
        actionProc.doneNotice = doneNotice || ""
        actionProc.command = [cli].concat(args)
        actionProc.running = true
    }

    function fetchRecipe(id) {
        var f = Object.assign({}, fetching)
        f[id] = true
        fetching = f
        var p = fetchComponent.createObject(root, { recipeId: id, command: [cli, "recipe", "fetch", id, "--json"] })
        p.running = true
    }

    // Each Hub request is its own process; only the answer to the latest one is kept, so a slow
    // earlier answer never mixes with what is selected now.
    property int searchSeq: 0
    property int repoSeq: 0

    function search(query, kind) {
        searching = true
        searchResults = []
        var args = [cli, "hub", "search", query, "--json"]
        if (kind) args.splice(4, 0, "--kind", kind)
        searchSeq++
        hubComponent.createObject(root, { kind: "search", seq: searchSeq, command: args }).running = true
    }

    function openRepo(repo) {
        loadingRepo = true
        repoDetail = null
        repoSeq++
        hubComponent.createObject(root, { kind: "repo", seq: repoSeq, command: [cli, "hub", "files", repo, "--json"] }).running = true
    }

    function chat(model, messages) {
        if (chatProc.running) return
        chatProc.request = JSON.stringify({ model: model, messages: messages,
                                            chat_template_kwargs: { enable_thinking: false } })
        chatProc.running = true
    }

    function stopChat() {
        if (chatProc.running) chatProc.signal(15)
    }

    function video(prompt, size, seconds, turbo) {
        if (videoProc.running) return
        var args = [cli, "video", "--prompt", prompt, "--size", size, "--seconds", String(seconds)]
        if (!turbo) args.push("--no-turbo")
        videoProc.command = args
        videoProc.running = true
    }

    function stopVideo() {
        if (videoProc.running) videoProc.signal(15)
    }

    function open(path) {
        openProc.command = ["xdg-open", path]
        openProc.running = true
    }

    function copy(text) {
        copyProc.command = ["wl-copy", "--", text]
        copyProc.running = true
    }

    function launchAgent(args) {
        launchProc.command = ["omarchy-launch-tui"].concat(args)
        launchProc.running = true
    }

    Timer { interval: 5000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
    Timer {
        interval: 2000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: {
            if (!statsProc.running) statsProc.running = true
            if (!instancesProc.running) instancesProc.running = true
            if (!downloadsProc.running) downloadsProc.running = true
        }
    }

    Process {
        id: recipesProc
        command: [root.cli, "recipes", "--json"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                var d = root.parse(text, null)
                if (d) { root.recipes = d.recipes || []; root.refusedRecipes = d.refused || [] }
            }
        }
    }
    Process {
        id: ollamaProc
        command: [root.cli, "ollama", "models", "--json"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: { var d = root.parse(text, []); root.ollamaModels = Array.isArray(d) ? d : [] }
        }
    }
    Process {
        id: modelsProc
        command: [root.cli, "models", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.models = root.parse(text, root.models) }
    }
    Process {
        id: instancesProc
        command: [root.cli, "instances", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.instances = root.parse(text, root.instances) }
    }
    Process {
        id: agentsProc
        command: [root.cli, "agents", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.agents = root.parse(text, root.agents) }
    }
    Process {
        id: downloadsProc
        command: [root.cli, "downloads", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.downloads = root.parse(text, root.downloads) }
    }
    Process {
        id: enginesProc
        command: [root.cli, "engines", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.engines = root.parse(text, root.engines) }
    }
    Process {
        id: statsProc
        command: [root.cli, "stats", "--json"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                var s = root.parse(text, null)
                if (s) { root.previousStats = root.stats; root.stats = s }
            }
        }
    }
    Component {
        id: hubComponent
        Process {
            id: hubProc
            property string kind: ""
            property int seq: 0
            readonly property bool latest: seq === (kind === "search" ? root.searchSeq : root.repoSeq)
            stdout: StdioCollector {
                waitForEnd: true
                onStreamFinished: {
                    if (!hubProc.latest) return
                    if (hubProc.kind === "search") root.searchResults = root.parse(text, [])
                    else root.repoDetail = root.parse(text, null)
                }
            }
            stderr: StdioCollector { waitForEnd: true; onStreamFinished: if (hubProc.latest && String(text).trim()) root.lastError = String(text).trim() }
            onExited: {
                if (latest && kind === "search") root.searching = false
                if (latest && kind === "repo") root.loadingRepo = false
                destroy(1000)       // after the collectors have delivered
            }
        }
    }
    Process {
        id: actionProc
        property string doneNotice: ""
        // the CLI reports some failures as {"error": ...} on stdout (JSON-lines commands)
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                var d = root.parse(text, null)
                if (d && !Array.isArray(d) && d.error) root.lastError = String(d.error)
            }
        }
        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: if (String(text).trim()) root.lastError = String(text).trim().split("\n").pop()
        }
        onExited: function(exitCode) {
            root.busy = ""
            if (exitCode !== 0 && !root.lastError) root.lastError = "That did not work (exit " + exitCode + ")"
            if (exitCode === 0 && doneNotice) root.notice = doneNotice
            root.refresh()
        }
    }
    Process {
        id: chatProc
        property string request: ""
        command: [root.cli, "chat"]
        stdinEnabled: true
        onStarted: { write(request); stdinEnabled = false }
        stdout: SplitParser {
            onRead: function(line) {
                var d = root.parse(line, null)
                if (!d) return
                if (d.delta !== undefined) root.chatDelta(d.delta)
                else if (d.reasoning !== undefined) root.chatReasoning(d.reasoning)
                else if (d.error !== undefined) root.chatError(d.error)
                else if (d.done) root.chatDone(d)
            }
        }
        onExited: { stdinEnabled = true; root.chatEnded() }
    }
    Process {
        id: videoProc
        property bool reported: false
        onStarted: reported = false
        stdout: SplitParser {
            onRead: function(line) {
                var d = root.parse(line, null)
                if (!d) return
                if (d.done !== undefined) { videoProc.reported = true; root.videoDone(d.done, d.seconds || 0) }
                else if (d.error !== undefined) { videoProc.reported = true; root.videoError(d.error) }
            }
        }
        onExited: function(exitCode) {
            if (!reported && exitCode !== 0) root.videoError("the video command ended without a result (exit " + exitCode + ")")
            root.videoEnded()
        }
    }
    Process { id: openProc }
    Process { id: copyProc; onExited: function(code) { if (code === 0) root.notice = "Endpoint copied" } }
    Process { id: launchProc }

    Component {
        id: fetchComponent
        Process {
            property string recipeId: ""
            stderr: StdioCollector { waitForEnd: true; onStreamFinished: if (String(text).trim()) root.lastError = String(text).trim().split("\n").pop() }
            onExited: {
                var f = Object.assign({}, root.fetching)
                delete f[recipeId]
                root.fetching = f
                root.refresh()
                destroy()
            }
        }
    }
}
