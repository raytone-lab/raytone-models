import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

ColumnLayout {
    id: page
    property var backend
    property bool streaming: false
    property string lastStats: ""
    readonly property var ready: page.backend.instances.filter(function (i) { return i.ready })
    spacing: 14

    ListModel { id: messages }

    function send() {
        var text = input.text.trim()
        if (!text || streaming || model.currentIndex < 0) return
        messages.append({ role: "user", content: text })
        var history = []
        for (var i = 0; i < messages.count; i++) history.push({ role: messages.get(i).role, content: messages.get(i).content })
        messages.append({ role: "assistant", content: "" })
        input.text = ""
        streaming = true
        lastStats = ""
        page.backend.chat(page.ready[model.currentIndex].served_name, history)
    }

    Connections {
        target: page.backend
        function onChatDelta(text) {
            var last = messages.count - 1
            messages.setProperty(last, "content", messages.get(last).content + text)
            list.positionViewAtEnd()
        }
        function onChatDone(summary) {
            page.streaming = false
            var u = summary.usage || {}
            var gen = summary.seconds - (summary.first_token_seconds || 0)
            page.lastStats = (u.completion_tokens || 0) + " tokens · first token " + (summary.first_token_seconds || 0).toFixed(2)
                + " s · " + (gen > 0 ? (u.completion_tokens / gen).toFixed(1) : "—") + " tokens/s"
        }
        function onChatEnded() { page.streaming = false }
        function onChatError(message) {
            page.streaming = false
            var last = messages.count - 1
            messages.setProperty(last, "content", "! " + message)
        }
    }

    PageHeader {
        title: "Chat"
        subtitle: "Try a running model before you hand it to an agent."
        RComboBox {
            id: model
            model: page.ready.map(function (i) { return i.served_name })
            implicitWidth: 260
            enabled: page.ready.length > 0
            displayText: page.ready.length ? currentText : "No model running"
        }
        RButton { text: "New chat"; onClicked: { messages.clear(); page.lastStats = "" } }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        radius: Theme.radiusCard
        color: Theme.surface
        border.color: Theme.border
        Text {
            anchors.centerIn: parent
            visible: messages.count === 0
            text: page.ready.length ? "Ask " + model.currentText + " anything." : "Start a model on Recipes or Local models to chat."
            color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody
        }
        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 18
            clip: true
            spacing: 14
            model: messages
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                id: msg
                required property string role
                required property string content
                width: list.width
                implicitHeight: bubble.implicitHeight
                Rectangle {
                    id: bubble
                    anchors.right: msg.role === "user" ? parent.right : undefined
                    width: Math.min(list.width * 0.78, body.implicitWidth + 28)
                    implicitHeight: body.implicitHeight + 20
                    radius: Theme.radiusCallout
                    color: msg.role === "user" ? Theme.raised : "transparent"
                    border.color: msg.role === "user" ? "transparent" : Theme.border
                    TextEdit {
                        id: body
                        anchors.fill: parent
                        anchors.margins: 10
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        text: msg.content || (page.streaming ? "…" : "")
                        color: msg.content.indexOf("! ") === 0 ? Theme.errorText : Theme.text
                        font.family: Theme.font
                        font.pixelSize: Theme.sizeNav
                        wrapMode: TextEdit.Wrap
                        readOnly: true
                        selectByMouse: true
                        textFormat: TextEdit.PlainText
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Math.min(140, Math.max(46, input.implicitHeight + 16))
            radius: 23
            color: Theme.surface
            border.color: input.activeFocus ? Theme.focus : Theme.border
            border.width: input.activeFocus ? 2 : 1
            ScrollView {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 6
                anchors.bottomMargin: 6
                TextArea {
                    id: input
                    placeholderText: "Message the model (Enter to send, Shift+Enter for a new line)"
                    placeholderTextColor: Theme.muted
                    color: Theme.text
                    font.family: Theme.font
                    font.pixelSize: Theme.sizeNav
                    wrapMode: TextArea.Wrap
                    background: null
                    Keys.onReturnPressed: function(event) { if (event.modifiers & Qt.ShiftModifier) event.accepted = false; else page.send() }
                }
            }
        }
        RButton {
            variant: page.streaming ? "danger" : "primary"
            text: page.streaming ? "Stop" : "Send"
            enabled: page.streaming || (input.text.trim() !== "" && page.ready.length > 0)
            onClicked: page.streaming ? page.backend.stopChat() : page.send()
        }
    }
    Text { text: page.lastStats; visible: text !== ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
}
