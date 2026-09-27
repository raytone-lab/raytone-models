import QtQuick
import Quickshell
import Quickshell.Io

// The app's Backend API over fixture files (design/mockups/data, real output from the Thor), for
// rendering the pages without the CLI.
Item {
    id: root
    property string dataDir: Quickshell.env("RAYTONE_UI_DATA")
    property var recipes: parse(recipesFile.text()).recipes || []
    property var refusedRecipes: []
    property var models: parse(modelsFile.text()) || []
    property var instances: parse(instancesFile.text()) || []
    property var agents: (parse(agentsFile.text()) || []).map(function (a) { return Object.assign({ connected: a.id === "opencode" || a.id === "claude" }, a) })
    property var downloads: [{ id: "d1", repo: "unsloth/Qwen3.8-27B-GGUF", revision: "4ca72078", state: "running", done: 8.1e9, expected: 19.3e9, progress: 0.42 }]
    property var engines: [
        { engine: "vllm", image: "vllm/vllm-openai@sha256:8a69ffad015f138d7170c4ddc429e230a3bc1c1719f67e14324749df200a4b90", tag: "v0.30.0", checked: "2026-09-27, Jetson AGX Thor: sm_110", configured: true },
        { engine: "sglang", image: null, configured: false }, { engine: "llamacpp", image: null, configured: false },
        { engine: "ollama", image: null, configured: false }, { engine: "comfyui", image: null, configured: false }]
    property var previousStats: ({ time: 100, memory: { total: 130595930112, available: 55000000000 }, instances: [{ id: "qwen3-8-27b", counters: { generation_tokens: 1000 } }] })
    property var stats: ({ time: 102, memory: { total: 130595930112, available: 52000000000 }, instances: [{ id: "qwen3-8-27b", counters: { generation_tokens: 1049 } }] })
    property var searchResults: (parse(discoverFile.text()) || {}).search || []
    property var repoDetail: parse(discoverFile.text())
    property bool searching: false
    property bool loadingRepo: false
    property string busy: ""
    property string lastError: ""
    property string notice: ""
    property var fetching: ({})
    signal chatDelta(string text)
    signal chatReasoning(string text)
    signal chatDone(var summary)
    signal chatError(string message)
    signal chatEnded()
    signal videoDone(string path, real seconds)
    signal videoError(string message)
    signal videoEnded()

    function parse(t) { try { return JSON.parse(String(t || "")) } catch (e) { return null } }
    function refresh() {}
    function act(key, args, done) {}
    function fetchRecipe(id) {}
    function search(q, k) {}
    function openRepo(r) {}
    function chat(m, msgs) {}
    function stopChat() {}
    function copy(t) {}
    function launchAgent(c) {}
    function video(p, s, n, t) {}
    function stopVideo() {}
    function open(p) {}

    FileView { id: recipesFile; path: root.dataDir + "/recipes.json"; blockLoading: true }
    FileView { id: modelsFile; path: root.dataDir + "/models.json"; blockLoading: true }
    FileView { id: instancesFile; path: root.dataDir + "/instances.json"; blockLoading: true }
    FileView { id: agentsFile; path: root.dataDir + "/agents.json"; blockLoading: true }
    FileView { id: discoverFile; path: root.dataDir + "/discover.json"; blockLoading: true }
}
