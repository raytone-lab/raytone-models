import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

Flickable {
    id: scroll
    property var backend
    contentWidth: width
    contentHeight: page.implicitHeight
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; active: scroll.contentHeight > scroll.height }
    clip: true
    ColumnLayout {
        id: page
        width: scroll.width - (scroll.contentHeight > scroll.height ? 12 : 0)
        height: implicitHeight
        property var backend: scroll.backend
        property var history: []          // recent tokens/s samples of the first instance
        readonly property var first: page.backend.instances.length ? page.backend.instances[0] : null
        readonly property string firstId: first ? first.id : ""
        readonly property var rate: firstId ? Logic.tokensPerSecond(page.backend.previousStats, page.backend.stats, firstId) : null
        readonly property var mem: page.backend.stats ? page.backend.stats.memory : null
        spacing: 16

        onFirstIdChanged: history = []

        Connections {
            target: page.backend
            function onStatsChanged() {
                if (!page.firstId) return
                page.history = page.history.slice(1 - speedHistory.sampleLimit).concat([page.rate])
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
                        Text { textFormat: Text.PlainText; text: "SERVED MODEL"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold; Layout.fillWidth: true; wrapMode: Text.Wrap }
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

        GridLayout {
            Layout.fillWidth: true
            columns: width < 620 ? 1 : 2
            columnSpacing: 16; rowSpacing: 16
            visible: page.backend.instances.length > 0 || page.mem !== null
            Card {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Text { textFormat: Text.PlainText; text: "生成速度"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; font.weight: Font.Bold }
                RowLayout {
                    Text { textFormat: Text.PlainText; text: page.rate === null ? "—" : String(page.rate); color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeTelemetry; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; text: page.rate === null ? "暂无遥测" : "tokens/s"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; Layout.alignment: Qt.AlignBottom; bottomPadding: 8 }
                }
                HistoryGraph {
                    id: speedHistory
                    objectName: "running-speed-history"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    samples: page.history
                }
                Text { textFormat: Text.PlainText; text: "最近一分钟，每 2 秒采样"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Card {
                id: memCard
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                readonly property real used: page.mem ? page.mem.total - page.mem.available : 0
                Text { textFormat: Text.PlainText; text: "系统内存"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; font.weight: Font.Bold }
                RowLayout {
                    Text { textFormat: Text.PlainText; text: page.mem ? (memCard.used / 1073741824).toFixed(1) : "—"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeTelemetry; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; text: page.mem ? "/ " + (page.mem.total / 1073741824).toFixed(0) + " GiB" : ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; Layout.alignment: Qt.AlignBottom; bottomPadding: 8 }
                }
                ProgressLine { Layout.fillWidth: true; value: page.mem ? memCard.used / page.mem.total : 0 }
                Text { textFormat: Text.PlainText;
                    text: page.mem ? Math.round(100 * memCard.used / page.mem.total) + "% 已用 · " + (page.mem.available / 1073741824).toFixed(1) + " GiB 可用" : ""
                    color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption
                }
                Text { textFormat: Text.PlainText; text: "此处为系统内存读数；GPU 能力与显存须另行核对。"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }

        Card {
            Layout.fillWidth: true
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 4
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; text: "本机模型入口（配置值）"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Text { textFormat: Text.PlainText; text: (page.backend.connection && page.backend.connection.public ? page.backend.connection.public : "入口状态读取中"); color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeCard; font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; text: "仅在模型路由与实例就绪后可用"; color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeControl; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
                Item { Layout.fillWidth: true }
                RButton { text: "复制"; enabled: !!page.backend.connection; onClicked: page.backend.copy((page.backend.connection && page.backend.connection.public ? page.backend.connection.public : "入口状态读取中")) }
            }
        }

    }

}
