import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    property var history: []          // recent tokens/s samples of the first instance
    readonly property var first: page.backend.instances.length ? page.backend.instances[0] : null
    readonly property var rate: first ? Logic.tokensPerSecond(page.backend.previousStats, page.backend.stats, first.id) : null
    readonly property var mem: page.backend.stats ? page.backend.stats.memory : null
    spacing: 16

    Connections {
        target: page.backend
        function onStatsChanged() {
            if (page.rate === null) return
            var h = page.history.slice(-29)
            h.push(page.rate)
            page.history = h
        }
    }

    PageHeader {
        title: "运行中"
        subtitle: "查看本机实例的真实状态与资源使用。"
        Pill { text: page.backend.instances.filter(function (i) { return i.ready }).length + " running"; kind: "ready"; visible: page.backend.instances.length > 0 }
    }

    Text { textFormat: Text.PlainText;
        visible: page.backend.instances.length === 0 && !page.backend.pageState
        text: "No models running. Apply a recipe, or run a local model."
        color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody
    }

    Repeater {
        model: page.backend.instances
        delegate: Card {
            id: inst
            required property var modelData
            Layout.fillWidth: true
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 4
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; text: "SERVED MODEL"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold }
                    Text { textFormat: Text.PlainText; text: inst.modelData.served_name; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeFeatured; font.weight: Font.Bold }
                }
                Item { Layout.fillWidth: true }
                Pill { text: inst.modelData.ready ? "就绪" : "尚未就绪"; kind: inst.modelData.ready ? "ready" : "pending" }
                Pill { text: "Agents use this"; kind: "ready"; visible: inst.modelData.current === true }
                RButton {
                    // agents ask for "local"; the router sends it to the current model
                    visible: inst.modelData.chat !== false && inst.modelData.current !== true && inst.modelData.ready
                    text: "Use for agents"
                    enabled: page.backend.busy === ""
                    onClicked: page.backend.act("use:" + inst.modelData.id, ["use", inst.modelData.served_name, "--json"], "Agents now use " + inst.modelData.served_name)
                }
                RButton {
                    variant: "danger"
                    text: page.backend.busy === "stop:" + inst.modelData.id ? "Stopping…" : "停止"
                    enabled: page.backend.busy === ""
                    onClicked: page.backend.act("stop:" + inst.modelData.id, ["stop", inst.modelData.id, "--json"], "Stopped " + inst.modelData.served_name)
                }
            }
            RowLayout {
                spacing: 60
                Repeater {
                    model: [["Engine", inst.modelData.engine === "vllm" ? "vLLM" : inst.modelData.engine],
                            ["Local port", String(inst.modelData.port)],
                            ["Context length", inst.modelData.context ? Number(inst.modelData.context).toLocaleString(Qt.locale("en_US"), "f", 0) + " tokens" : "—"]]
                    delegate: ColumnLayout {
                        required property var modelData
                        spacing: 2
                        Text { textFormat: Text.PlainText; text: parent.modelData[0]; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeControl }
                        Text { textFormat: Text.PlainText; text: parent.modelData[1]; color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        visible: page.backend.instances.length > 0 || page.mem !== null
        Card {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            Text { textFormat: Text.PlainText; text: "GENERATION SPEED"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; font.weight: Font.Bold }
            RowLayout {
                Text { textFormat: Text.PlainText; text: page.rate === null ? "—" : String(page.rate); color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeTelemetry; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; text: page.rate === null ? "Waiting for telemetry" : "tokens/s"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; Layout.alignment: Qt.AlignBottom; bottomPadding: 8 }
            }
            Row {
                spacing: 6
                height: 48
                Repeater {
                    model: page.history
                    delegate: Rectangle {
                        required property var modelData
                        readonly property real peak: Math.max(1, Math.max.apply(null, page.history))
                        width: 9
                        height: Math.max(3, 48 * modelData / peak)
                        anchors.bottom: parent.bottom
                        radius: 4
                        color: Theme.accent
                    }
                }
            }
            Text { textFormat: Text.PlainText; text: "Last minute, sampled every 2 s"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
        }
        Card {
            id: memCard
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            readonly property real used: page.mem ? page.mem.total - page.mem.available : 0
            Text { textFormat: Text.PlainText; text: "UNIFIED MEMORY"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; font.weight: Font.Bold }
            RowLayout {
                Text { textFormat: Text.PlainText; text: page.mem ? (memCard.used / 1073741824).toFixed(1) : "—"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeTelemetry; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; text: page.mem ? "/ " + (page.mem.total / 1073741824).toFixed(0) + " GiB" : ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; Layout.alignment: Qt.AlignBottom; bottomPadding: 8 }
            }
            ProgressLine { Layout.fillWidth: true; value: page.mem ? memCard.used / page.mem.total : 0 }
            Text { textFormat: Text.PlainText;
                text: page.mem ? Math.round(100 * memCard.used / page.mem.total) + "% in use · " + (page.mem.available / 1073741824).toFixed(1) + " GiB available" : ""
                color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption
            }
            Text { textFormat: Text.PlainText; text: "CPU and GPU share this memory on the Jetson AGX Thor."; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
        }
    }

    Card {
        Layout.fillWidth: true
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 4
                Layout.fillWidth: true
                Text { textFormat: Text.PlainText; text: "LOCAL ROUTER · OPENAI- AND ANTHROPIC-COMPATIBLE"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold }
                Text { textFormat: Text.PlainText; text: "http://127.0.0.1:8090/v1"; color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeCard; font.weight: Font.DemiBold }
                Text { textFormat: Text.PlainText; text: "model \"local\" is always the current model"; color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeControl }
            }
            Item { Layout.fillWidth: true }
            RButton { text: "Copy"; onClicked: page.backend.copy("http://127.0.0.1:8090/v1") }
        }
    }

    Item { Layout.fillHeight: true }
}
