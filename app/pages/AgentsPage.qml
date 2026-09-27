import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    readonly property var connectable: page.backend.agents.filter(function (a) { return a.connectable })
    readonly property var later: page.backend.agents.filter(function (a) { return a.supported && !a.connectable })
    readonly property var unsupported: page.backend.agents.filter(function (a) { return !a.supported })
    readonly property var chatModels: Logic.chatModels(page.backend.instances)
    readonly property bool modelReady: chatModels.length > 0
    spacing: 14

    PageHeader {
        title: "Agents"
        subtitle: "Point Omarchy's coding agents at your local models. Revert puts their settings back exactly."
        Pill { text: page.backend.agents.length + " coding agents"; kind: "neutral" }
    }

    Card {
        Layout.fillWidth: true
        padding: 16
        Text { text: "One local endpoint for every agent"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold }
        Text {
            text: "http://127.0.0.1:8090/v1 · " + (page.modelReady ? page.chatModels.map(function (i) { return i.served_name }).join(", ")
                                                 : "start a model first")
            color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeControl
        }
    }

    ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: parent.width
            spacing: 12
            GridLayout {
                columns: 2
                columnSpacing: 14
                rowSpacing: 14
                Layout.fillWidth: true
                Repeater {
                    model: page.connectable
                    delegate: Card {
                        id: a
                        required property var modelData
                        readonly property var command: Logic.launchArgs(modelData.id)
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        padding: 16
                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout {
                                spacing: 6
                                Layout.fillWidth: true
                                Text { text: a.modelData.name; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeCard; font.weight: Font.Bold }
                                Pill { text: a.modelData.connected ? "Connected" : "Not connected"; kind: a.modelData.connected ? "ready" : "neutral" }
                            }
                            Item { Layout.fillWidth: true }
                            RButton {
                                visible: a.modelData.connected
                                text: "Revert"
                                enabled: page.backend.busy === ""
                                onClicked: page.backend.act("agent:" + a.modelData.id, ["agent", "revert", a.modelData.id, "--json"], a.modelData.name + " settings restored")
                            }
                            RButton {
                                visible: a.modelData.connected && a.command !== null
                                text: "Launch"
                                onClicked: page.backend.launchAgent(a.command)
                            }
                            RButton {
                                visible: !a.modelData.connected
                                variant: "primary"
                                text: page.backend.busy === "agent:" + a.modelData.id ? "Connecting…" : "Connect"
                                enabled: page.backend.busy === "" && page.modelReady
                                ToolTip.visible: hovered && !page.modelReady
                                ToolTip.text: "Start a compatible model first"
                                onClicked: page.backend.act("agent:" + a.modelData.id, ["agent", "connect", a.modelData.id, "--json"], a.modelData.name + " connected")
                            }
                        }
                    }
                }
            }
            Text { text: "Supported later"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold; topPadding: 6 }
            GridLayout {
                columns: 3
                columnSpacing: 12
                rowSpacing: 12
                Layout.fillWidth: true
                Repeater {
                    model: page.later
                    delegate: Card {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        padding: 14
                        Text { text: modelData.name; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold }
                        Text { text: modelData.note || "Connection support planned"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
            }
            Text { text: "Unavailable"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold; topPadding: 6 }
            GridLayout {
                columns: 3
                columnSpacing: 12
                rowSpacing: 12
                Layout.fillWidth: true
                Repeater {
                    model: page.unsupported
                    delegate: Card {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        padding: 14
                        color: Theme.raised
                        Text { text: modelData.name; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold }
                        Text { text: modelData.reason; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
            }
        }
    }
}
