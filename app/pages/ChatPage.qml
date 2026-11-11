import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    signal openModels()
    property bool streaming: false
    property string lastStats: ""
    property string submitted: ""
    property string selectedModel: ""
    readonly property var ready: Logic.chatModels(page.backend.instances)
    spacing: 14

    ListModel { id: messages }

    function messageEntries() {
        var entries = []
        for (var i = 0; i < messages.count; i++)
            entries.push({ role: messages.get(i).role, content: messages.get(i).content })
        return entries
    }

    // Read-only transcript hooks for probes and accessibility; they do not mutate state.
    function messagesCount() { return messages.count }
    function messageRole(i) { return messages.get(i).role }
    function messageContent(i) { return messages.get(i).content }

    function send() {
        var text = input.text.trim()
        if (streaming || !Logic.chatSendAllowed(text, model.currentIndex, page.ready.length)) return
        var chosen = page.ready[model.currentIndex].served_name
        page.selectedModel = chosen
        messages.append({ role: "user", content: text })
        var history = Logic.chatHistory(messageEntries())
        messages.append({ role: "assistant", content: "" })
        page.submitted = text
        input.text = ""
        streaming = true
        lastStats = ""
        page.backend.chat(chosen, history)
    }

    Connections {
        target: page.backend
        function onChatDelta(text) {
            var last = messages.count - 1
            if (last < 0 || messages.get(last).role !== "assistant") return
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
            // An error is UI state, never assistant content (V1.1 D03/R07). With no reply
            // received the failed turn is rolled back and the draft restored, so retrying
            // resubmits the question once instead of duplicating it in the history. With a
            // partial reply the received text stays a real assistant turn and the failure
            // becomes a separate entry; the draft is not force-restored over new typing.
            if (last >= 0 && messages.get(last).role === "assistant" && messages.get(last).content === "") {
                messages.remove(last)
                if (messages.count > 0 && messages.get(messages.count - 1).role === "user")
                    messages.remove(messages.count - 1)
                if (input.text === "") input.text = page.submitted
            } else {
                messages.append({ role: "error", content: message })
            }
        }
    }

    PageHeader {
        title: "对话"
        subtitle: "默认使用当前本地模型；此处另选仅影响本次对话。"
        RComboBox {
            id: model
            objectName: "chatModelSelection"
            onActivated: page.selectedModel=currentText
            readonly property int desiredIndex: Logic.chatSelectionIndex(page.ready, page.selectedModel)
            function syncSelection() { model.currentIndex = model.desiredIndex }
            // ComboBox resets its index when an array model is replaced. Apply
            // identity selection after that reset, including same-order polls.
            onDesiredIndexChanged: Qt.callLater(syncSelection)
            onModelChanged: Qt.callLater(syncSelection)
            Component.onCompleted: Qt.callLater(syncSelection)
            model: page.ready.map(function (i) { return i.served_name })
            implicitWidth: 260
            enabled: page.ready.length > 0
            displayText: currentIndex >= 0 ? currentText : (page.ready.length ? "请选择就绪模型" : "暂无就绪模型")
        }
        // not while a reply streams in: its deltas belong to the conversation on screen
        RButton { text: "选择模型"; visible: !page.ready.length; onClicked: page.openModels() }
        RButton { text: "新对话"; visible: page.ready.length > 0; enabled: !page.streaming; onClicked: { messages.clear(); page.lastStats = "" } }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        radius: Theme.radiusCard
        color: Theme.surface
        border.color: Theme.border
        Text { textFormat: Text.PlainText;
            anchors.centerIn: parent
            width: parent.width - 32
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            visible: messages.count === 0
            text: model.currentIndex >= 0 ? "向 " + model.currentText + " 提问。" : (page.ready.length ? "当前选择不可用，请明确选择一个就绪模型。" : "请先在配方或本地模型中启动适用的模型。")
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
                        color: msg.role === "error" ? Theme.errorText : Theme.text
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
                    objectName: "chatDraft"
                    placeholderText: "输入消息（Enter 发送，Shift+Enter 换行）"
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
            objectName: "chatSendButton"
            variant: page.streaming ? "danger" : "primary"
            text: page.streaming ? "停止" : "发送"
            enabled: page.streaming || Logic.chatSendAllowed(input.text, model.currentIndex, page.ready.length)
            onClicked: page.streaming ? page.backend.stopChat() : page.send()
        }
    }
    Text { textFormat: Text.PlainText; text: page.lastStats; visible: text !== ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
}
