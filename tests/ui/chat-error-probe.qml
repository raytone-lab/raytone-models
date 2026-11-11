import QtQuick
import Quickshell
import "app/components"
import "app/pages"

// V1.1 D03/R07 probe: a failed turn must never put error text into the model-bound
// history, the send button and send() must agree on model validity, and a user stop
// is a clean end, not a failure. Run on a box with Quickshell:
//   quickshell -p tests/ui/chat-error-probe.qml
// PASS/FAIL lines are prefixed CHAT_PROBE_.
ShellRoot {
    FloatingWindow {
        implicitWidth: 1000
        implicitHeight: 720
        visible: true

        QtObject {
            id: fixture
            property var instances: [instance("qwen", true)]
            property var requests: []          // every chat() call: {model, messages}
            property string stopped: ""

            function instance(id, cur) {
                return { id: id, served_name: id, ready: true, current: cur, engine: "vllm", port: 18001, chat: true }
            }

            signal chatDelta(string text)
            signal chatReasoning(string text)
            signal chatDone(var summary)
            signal chatError(string message)
            signal chatEnded()

            function chat(model, messages) { requests.push({ model: model, messages: messages }) }
            function stopChat() { stopped = "requested"; chatEnded() }  // what Backend now does for a user stop
        }

        ChatPage { id: page; backend: fixture; width: parent.width; height: parent.height }

        Timer {
            interval: 250
            repeat: true
            running: true
            property int phase: 0
            property int failures: 0

            function findItem(item, name) {
                if (item.objectName === name) return item
                for (const child of item.children) {
                    const found = findItem(child, name)
                    if (found) return found
                }
                return null
            }
            function check(value, name) {
                if (value) return
                failures++
                console.log("CHAT_PROBE_FAIL", name)
            }
            function lastRequest() { return fixture.requests[fixture.requests.length - 1] }

            onTriggered: {
                const input = findItem(page, "chatDraft")
                const combo = findItem(page, "chatModelSelection")
                const button = findItem(page, "chatSendButton")
                if (!input || !combo || !button) {
                    check(false, "chat controls missing")
                    Qt.quit()
                    return
                }
                if (phase === 0) {
                    // selection settles via Qt.callLater; after that the button tracks text+selection
                    check(combo.currentIndex === 0, "current chat model auto-selected")
                    check(!button.enabled, "send disabled with empty draft")
                    input.text = "  "
                    check(!button.enabled, "send disabled with blank draft")
                    input.text = "你好"
                    check(button.enabled, "send enabled with draft and selection")
                    combo.currentIndex = -1
                    check(!button.enabled, "send disabled without a selected model")
                    page.send()
                    check(fixture.requests.length === 0, "send() refuses without a selected model")
                    combo.currentIndex = 0
                    page.send()
                    check(fixture.requests.length === 1, "send() goes through with a selected model")
                    check(lastRequest().model === "qwen", "request names the chosen model")
                    check(JSON.stringify(lastRequest().messages) === JSON.stringify([{ role: "user", content: "你好" }]),
                          "first request history is exactly the user turn")
                } else if (phase === 1) {
                    // failure before any content: the turn rolls back, the draft comes back
                    fixture.chatError("引擎未就绪")
                    check(page.streaming === false, "streaming cleared on error")
                    check(page.messagesCount() === 0, "failed turn rolled back out of the transcript")
                    check(input.text === "你好", "draft restored after a failed turn")
                    check(button.enabled, "send enabled again after rollback")
                    page.send()
                    check(fixture.requests.length === 2, "retry sends once")
                    check(JSON.stringify(lastRequest().messages) === JSON.stringify([{ role: "user", content: "你好" }]),
                          "retry history has no duplicate and no error text")
                } else if (phase === 2) {
                    // failure after partial content: the partial reply stays, the error is separate
                    fixture.chatDelta("部分回答")
                    fixture.chatError("连接断开")
                    check(page.messagesCount() === 3, "partial turn keeps user, assistant and error entries")
                    check(page.messageRole(1) === "assistant" && page.messageContent(1) === "部分回答",
                          "received partial text stays assistant content")
                    check(page.messageRole(2) === "error", "failure lands in its own error entry")
                    check(input.text === "", "draft not force-restored over the standing partial turn")
                    input.text = "继续"
                    page.send()
                    check(JSON.stringify(lastRequest().messages) === JSON.stringify([
                        { role: "user", content: "你好" }, { role: "assistant", content: "部分回答" }, { role: "user", content: "继续" }
                    ]), "follow-up history keeps the partial answer and excludes the error entry")
                } else if (phase === 3) {
                    // user stop: clean end, partial kept, nothing reported as failure.
                    // The phase-2 error entry legitimately stays until a new conversation;
                    // a stop must not add another entry or mutate the reply.
                    const before = page.messagesCount()
                    fixture.chatDelta("更多")
                    fixture.stopChat()
                    check(page.streaming === false, "streaming cleared after user stop")
                    check(page.messagesCount() === before, "a user stop adds no error entry")
                    check(page.messageRole(page.messagesCount() - 1) === "assistant"
                          && page.messageContent(page.messagesCount() - 1) === "更多",
                          "partial content survives the stop")
                    // ready list empties: button and send() both refuse
                    fixture.instances = []
                    input.text = "再问"
                    check(!button.enabled, "send disabled when no model is ready")
                    page.send()
                    check(fixture.requests.length === 3, "send() refuses when no model is ready")
                } else {
                    if (failures === 0) console.log("CHAT_PROBE_PASS")
                    Qt.quit()
                }
                phase++
            }
        }
    }
}
