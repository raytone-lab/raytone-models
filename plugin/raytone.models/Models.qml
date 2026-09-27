pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import "ModelsLogic.js" as Logic

// Raytone Models panel: running instances, local models, agents. Every action is a
// `raytone-models ... --json` call; the panel keeps no state of its own.
Item {
    id: root

    property var shell: null
    property var manifest: null
    property bool opened: false
    property var targetScreen: null
    property var models: []
    property var instances: []
    property var agentList: []
    property var recipeList: []
    property string busyKey: ""
    property string message: ""

    function open(_payloadJson) {
        message = ""
        targetScreen = focusedScreen() || (Quickshell.screens.length > 0 ? Quickshell.screens[0] : null)
        opened = true
        refresh()
    }

    function close() {
        opened = false
    }

    function dismiss() {
        if (shell && typeof shell.hide === "function") shell.hide((manifest && manifest.id) || "raytone.models")
        else root.close()
    }

    function focusedScreen() {
        var monitor = Hyprland.focusedMonitor
        if (!monitor) return null
        for (var i = 0; i < Quickshell.screens.length; i++)
            if (String(Quickshell.screens[i].name || "") === String(monitor.name || "")) return Quickshell.screens[i]
        return null
    }

    function parse(text, fallback) {
        try { return JSON.parse(String(text || "")) } catch (e) { return fallback }
    }

    function refresh() {
        if (!opened) return
        if (!modelsProc.running) modelsProc.running = true
        if (!instancesProc.running) instancesProc.running = true
        if (!agentsProc.running) agentsProc.running = true
        if (!recipesProc.running) recipesProc.running = true
    }

    function act(key, argv) {
        if (actionProc.running) return
        busyKey = key
        message = ""
        actionProc.command = argv
        actionProc.running = true
    }

    function readyModels() {
        var n = 0
        for (var i = 0; i < instances.length; i++) if (instances[i].ready) n++
        return n
    }

    Timer {
        interval: 3000
        repeat: true
        running: root.opened
        onTriggered: root.refresh()
    }

    Process {
        id: modelsProc
        command: ["raytone-models", "models", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.models = root.parse(text, []) }
    }
    Process {
        id: instancesProc
        command: ["raytone-models", "instances", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.instances = root.parse(text, []) }
    }
    Process {
        id: agentsProc
        command: ["raytone-models", "agents", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.agentList = root.parse(text, []) }
    }
    Process {
        id: recipesProc
        command: ["raytone-models", "recipes", "--json"]
        stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.recipeList = (root.parse(text, {}).recipes || []) }
    }
    Process {
        id: actionProc
        stdout: StdioCollector { waitForEnd: true }
        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: if (String(text).trim() !== "") root.message = String(text).trim().split("\n").pop()
        }
        onExited: function(exitCode) {
            root.busyKey = ""
            if (exitCode === 0 && root.message === "") root.message = "Done."
            root.refresh()
        }
    }

    PanelWindow {
        id: panel
        screen: root.targetScreen
        visible: root.opened
        implicitWidth: 520
        implicitHeight: Math.min((root.targetScreen ? root.targetScreen.height : 900) - 72, content.implicitHeight + 32)
        color: Theme.transparent
        mask: Region { item: surface }
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "raytone-models"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
        HyprlandFocusGrab { active: root.opened; windows: [panel]; onCleared: root.dismiss() }
        anchors { top: true; right: true }
        margins.top: 36
        margins.right: 12

        Rectangle {
            id: surface
            anchors.fill: parent
            color: Theme.surfaceTranslucent
            border.color: Theme.separator
            border.width: 1
            radius: Theme.radiusCard
            focus: root.opened
            Keys.onEscapePressed: root.dismiss()

            Flickable {
                anchors.fill: parent
                anchors.margins: 16
                contentHeight: content.implicitHeight
                clip: true

                ColumnLayout {
                    id: content
                    width: parent.width
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "Raytone Models"
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontTitle
                            font.bold: true
                            Layout.fillWidth: true
                        }
                        Text {
                            text: root.readyModels() + " running · 127.0.0.1:8090"
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontCaption
                        }
                    }

                    SectionTitle { text: "Recipes · Raytone AI Lab" }
                    Repeater {
                        model: root.recipeList
                        delegate: Row3 {
                            required property var modelData
                            title: modelData.title
                            detail: Logic.recipeDetail(modelData)
                            status: modelData.running ? "running" : (modelData.state === "ready" ? "ready" : "not downloaded")
                            statusColor: modelData.running ? Theme.success : (modelData.state === "ready" ? Theme.textMuted : Theme.warning)
                            actionText: Logic.recipeAction(modelData, root.busyKey === "recipe:" + modelData.id)
                            actionEnabled: root.busyKey === ""
                            onAction: root.act("recipe:" + modelData.id, Logic.recipeArgv(modelData))
                        }
                    }

                    SectionTitle { text: "Running" }
                    Text {
                        visible: root.instances.length === 0
                        text: "No model is running. Start one below."
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontLabel
                    }
                    Repeater {
                        model: root.instances
                        delegate: Row3 {
                            required property var modelData
                            title: modelData.served_name
                            detail: modelData.engine + " · port " + modelData.port + (modelData.context ? " · " + modelData.context + " ctx" : "")
                            status: modelData.ready ? "ready" : "starting"
                            statusColor: modelData.ready ? Theme.success : Theme.warning
                            actionText: root.busyKey === "stop:" + modelData.id ? "Stopping…" : "Stop"
                            actionEnabled: root.busyKey === ""
                            onAction: root.act("stop:" + modelData.id, ["raytone-models", "stop", modelData.id, "--json"])
                        }
                    }

                    SectionTitle { text: "Local models" }
                    Repeater {
                        model: root.models
                        delegate: Row3 {
                            required property var modelData
                            title: String(modelData.repo).split("/").pop()
                            detail: modelData.repo.split("/")[0] + " · " + Logic.gib(modelData.size)
                                    + (modelData.quant ? " · " + modelData.quant : "") + " · " + modelData.format
                            status: Logic.modelState(modelData)
                            statusColor: status === "ready" ? Theme.textMuted : Theme.warning
                            actionText: root.busyKey === "run:" + modelData.repo ? "Starting…" : "Run"
                            actionVisible: Logic.runnable(modelData)
                            actionEnabled: root.busyKey === ""
                            onAction: root.act("run:" + modelData.repo, Logic.runArgv(modelData.repo, modelData.revision))
                        }
                    }

                    SectionTitle { text: "Agents" }
                    Repeater {
                        model: root.agentList
                        delegate: Row3 {
                            required property var modelData
                            title: modelData.name
                            detail: modelData.supported ? (modelData.note || "Uses the running models through the router")
                                                        : "Not available: " + modelData.reason
                            status: ""
                            actionText: "Connect"
                            actionVisible: modelData.supported && modelData.id === "opencode"
                            actionEnabled: root.busyKey === "" && root.readyModels() > 0
                            secondaryText: "Revert"
                            secondaryVisible: actionVisible
                            secondaryEnabled: root.busyKey === ""    // reverting needs no running model
                            onAction: root.act("agent:" + modelData.id, ["raytone-models", "agent", "connect", modelData.id, "--json"])
                            onSecondary: root.act("agent:" + modelData.id, ["raytone-models", "agent", "revert", modelData.id, "--json"])
                        }
                    }

                    Text {
                        visible: root.message !== ""
                        text: root.message
                        color: root.message === "Done." ? Theme.success : Theme.error
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontLabel
                    }
                }
            }
        }
    }

    component SectionTitle: Text {
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontState
        font.bold: true
        topPadding: 6
    }

    component Row3: Rectangle {
        id: row
        property string title: ""
        property string detail: ""
        property string status: ""
        property color statusColor: Theme.textMuted
        property string actionText: ""
        property bool actionVisible: true
        property bool actionEnabled: true
        property string secondaryText: ""
        property bool secondaryVisible: false
        property bool secondaryEnabled: actionEnabled
        signal action()
        signal secondary()
        Layout.fillWidth: true
        implicitHeight: 58
        radius: Theme.radiusControl
        color: Theme.surface
        border.color: Theme.separator
        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: row.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCard; elide: Text.ElideRight; Layout.fillWidth: true }
                Text { text: row.detail; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontCaption; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            Text { visible: row.status !== ""; text: row.status; color: row.statusColor; font.family: Theme.fontFamily; font.pixelSize: Theme.fontState }
            RaytoneButton { visible: row.secondaryVisible; text: row.secondaryText; variant: "outline"; enabled: row.secondaryEnabled; onClicked: row.secondary() }
            RaytoneButton { visible: row.actionVisible; text: row.actionText; variant: "primary"; enabled: row.actionEnabled; onClicked: row.action() }
        }
    }
}
