import QtQuick
import Quickshell
import Quickshell.Io
import "components"

// Everything the app knows comes from `raytone-models ... --json`; the app keeps no model state of
// its own. Lists refresh while the window is open; one action runs at a time.
Item {
    id: root

    property string cli: Quickshell.env("RAYTONE_MODELS_CLI") || "/usr/lib/raytone-models/raytone-models"
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
    property bool searchAttempted: false
    property var lastSearch: null
    property bool searching: false
    property bool loadingRepo: false
    property string busy: ""           // the key of the action in flight
    property string lastError: ""
    property string notice: ""
    property var fetching: ({})        // recipe id -> true while `recipe fetch` runs
    property var readErrors: ({})
    property var loaded: ({})
    property var connection: null
    readonly property string connectionMessage: !connection ? "正在核对本机模型连接。"
        : (!connection.system.ready ? "系统组件未安装或版本不配套，模型启动、停止和删除暂不可用。"
           : (connection.router.code === "NO_INSTANCE" ? "当前没有可用于对话的本机模型。"
              : (!connection.router.ready ? "本机模型连接尚未就绪（" + connection.router.code + "）。" : "")))
    readonly property string readError: Object.keys(readErrors).map(function(k) { return k + ": " + readErrors[k] }).join("\n")

    function readFailed(key, message) {
        var next = Object.assign({}, readErrors); next[key] = message; readErrors = next
    }
    function readOk(key) {
        var seen = Object.assign({}, loaded); seen[key] = true; loaded = seen
        var next = Object.assign({}, readErrors); delete next[key]; readErrors = next
    }
    function readList(key, value) {
        if (!Array.isArray(value)) { readFailed(key, "列表格式无效。"); return }
        root[key] = value; readOk(key)
    }

    function pageState(keys, count, emptyMessage) {
        var failed=keys.filter(function(k) { return !!root.readErrors[k] })
        if (failed.length) {
            var message=failed.map(function(k) { return root.readErrors[k] }).join("\n")
            return {phase: /permission|authori[sz]|authentication|cancel|权限|授权/i.test(message) ? "denied" : "error", message:message}
        }
        if(keys.some(function(k) { return !root.loaded[k] })) return {phase:"loading",message:"正在读取实际状态…"}
        return {phase:count===0 ? "empty" : "ready",message:count===0 ? emptyMessage : ""}
    }
    function mutationAvailable() { return !!(connection && connection.system && connection.system.ready) }

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

    function startRead(process) {
        if (!process.running) { process.completed = false; process.running = true }
    }
    function refresh() {
        root.startRead(connectionProc)
        root.startRead(recipesProc)
        root.startRead(modelsProc)
        root.startRead(ollamaProc)
        root.startRead(instancesProc)
        root.startRead(agentsProc)
        root.startRead(downloadsProc)
        root.startRead(enginesProc)
    }

    // One action at a time; the key names it for the button that started it.
    function act(key, args, doneNotice) {
        if (actionProc.running) return
        busy = key
        notice = ""
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
        lastSearch = {query:query,kind:kind}
        searching = true
        searchAttempted = true
        var seen=Object.assign({},loaded);delete seen.search;loaded=seen
        readOk("search-request")
        var errors=Object.assign({}, readErrors);delete errors.search;readErrors=errors
        var args = [cli, "hub", "search", query, "--json"]
        if (kind) args.splice(4, 0, "--kind", kind)
        searchSeq++
        hubComponent.createObject(root, { kind: "search", seq: searchSeq, command: args }).running = true
    }

    function retrySearch() { if(lastSearch && !searching) search(lastSearch.query,lastSearch.kind) }

    function openRepo(repo) {
        loadingRepo = true
        repoDetail = null
        var errors=Object.assign({}, readErrors);delete errors.repo;readErrors=errors
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

    // an agent's own web UI (Hermes, OpenClaw): the CLI starts what it needs and opens it
    function launchWeb(id) {
        // Not execDetached: that discards stderr, and checking before opening is the whole reason
        // cmd_agent_web probes first -- naming the URL that went unanswered, and the clock, which
        // on this machine falls back to 1970 on a cold power loss and invalidates the certificate.
        // Detached, none of that could ever reach anyone: a workspace that was not serving made
        // the button do nothing at all, visibly. The chain ends in "exec setsid uwsm-app", which
        // returns once the browser is handed to systemd, so this exits promptly either way.
        // busy is left alone on purpose: opening a browser is not something the other buttons
        // should have to wait on, and a success notice for it would be noise.
        lastError = ""
        webProc.command = [root.cli, "agent-web", id]
        webProc.running = true
    }

    function launchAgent(args) {
        var actual = args.slice()
        var cliIndex = actual.indexOf("raytone-models")
        if (cliIndex >= 0) actual[cliIndex] = cli
        launchProc.command = ["omarchy-launch-tui"].concat(actual)
        launchProc.running = true
    }

    Timer { interval: 5000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
    Timer {
        interval: 2000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: {
            root.startRead(statsProc)
            root.startRead(instancesProc)
            root.startRead(downloadsProc)
        }
    }

    ReadProcess {
        id: connectionProc
        command: [root.cli, "status", "--json"]
        onResult: function(value) {
            value = root.parse(value, null);
            if (!value || value.kind !== "raytone-models" || value.schema !== 1) { root.readFailed("connection", "配套版本无效。"); return }
            root.connection = value; root.readOk("connection")
        }
        onFailed: function(message) { root.readFailed("connection", message) }
    }
    ReadProcess {
        id: recipesProc
        command: [root.cli, "recipes", "--json"]
        onResult: function(d) {
            d = root.parse(d, null);
            if (!d || !Array.isArray(d.recipes) || !Array.isArray(d.refused)) { root.readFailed("recipes", "配方数据格式无效。"); return }
            root.recipes = d.recipes; root.refusedRecipes = d.refused; root.readOk("recipes")
        }
        onFailed: function(message) { root.readFailed("recipes", message) }
    }
    ReadProcess {
        id: modelsProc
        command: [root.cli, "models", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("models", value) }
        onFailed: function(message) { root.readFailed("models", message) }
    }
    ReadProcess {
        id: ollamaProc
        command: [root.cli, "ollama", "models", "--optional", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("ollamaModels", value) }
        onFailed: function(message) { root.readFailed("ollamaModels", message) }
    }
    ReadProcess {
        id: instancesProc
        command: [root.cli, "instances", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("instances", value) }
        onFailed: function(message) { root.readFailed("instances", message) }
    }
    ReadProcess {
        id: agentsProc
        command: [root.cli, "agents", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("agents", value) }
        onFailed: function(message) { root.readFailed("agents", message) }
    }
    ReadProcess {
        id: downloadsProc
        command: [root.cli, "downloads", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("downloads", value) }
        onFailed: function(message) { root.readFailed("downloads", message) }
    }
    ReadProcess {
        id: enginesProc
        command: [root.cli, "engines", "--json"]
        onResult: function(value) {
            value = root.parse(value, null); root.readList("engines", value) }
        onFailed: function(message) { root.readFailed("engines", message) }
    }
    ReadProcess {
        id: statsProc
        command: [root.cli, "stats", "--json"]
        onResult: function(value) {
            value = root.parse(value, null);
            if (!value || !value.memory) { root.readFailed("stats", "统计数据格式无效。"); return }
            root.previousStats = root.stats; root.stats = value; root.readOk("stats")
        }
        onFailed: function(message) { root.readFailed("stats", message) }
    }
    Component {
        id: hubComponent
        ReadProcess {
            id: hubProc
            property string kind: ""
            property int seq: 0
            readonly property bool latest: seq === (kind === "search" ? root.searchSeq : root.repoSeq)
            function finish() {
                if(latest && kind === "search") root.searching=false
                if(latest && kind === "repo") root.loadingRepo=false
                destroy(1000)
            }
            onResult: function(text) {
                if(!latest) { finish();return }
                var value=root.parse(text,null)
                if(kind === "search" && Array.isArray(value)) { root.searchResults=value;root.readOk("search") }
                else if(kind === "repo" && value && Array.isArray(value.variants)) { root.repoDetail=value;root.readOk("repo") }
                else root.readFailed(kind,"返回的数据格式无效，请重试。")
                finish()
            }
            onFailed: function(message) { if(latest)root.readFailed(kind,message);finish() }
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
            if (exitCode === 0 && !root.lastError && doneNotice) root.notice = doneNotice
            root.refresh()
        }
    }
    Process {
        id: chatProc
        property bool reportedError: false
        property string diagnostic: ""
        property string request: ""
        command: [root.cli, "chat"]
        stdinEnabled: true
        onStarted: { reportedError=false;diagnostic="";write(request); stdinEnabled = false }
        stdout: SplitParser {
            onRead: function(line) {
                var d = root.parse(line, null)
                if (!d) return
                if (d.delta !== undefined) root.chatDelta(d.delta)
                else if (d.reasoning !== undefined) root.chatReasoning(d.reasoning)
                else if (d.error !== undefined) { chatProc.reportedError=true;root.chatError(d.error) }
                else if (d.done) root.chatDone(d)
            }
        }
        stderr: StdioCollector { waitForEnd:true;onStreamFinished:chatProc.diagnostic=String(text).trim().slice(-1000) }
        onExited: function(code) {
            if(code!==0 && !reportedError) root.chatError(diagnostic || "对话命令未完成（退出码 "+code+"）。")
            stdinEnabled = true; root.chatEnded()
        }
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
    Process {
        id: webProc
        stderr: StdioCollector { waitForEnd: true; onStreamFinished: if (String(text).trim()) root.lastError = String(text).trim().split("\n").pop() }
        onExited: function(exitCode) { if (exitCode !== 0 && !root.lastError) root.lastError = "That did not work (exit " + exitCode + ")" }
    }
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
