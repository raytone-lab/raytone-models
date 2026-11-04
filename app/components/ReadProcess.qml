import QtQuick
import Quickshell.Io

// Failed reads never replace the last good value with an empty collection.
Process {
    id: reader
    property string output: ""
    property string errorOutput: ""
    property bool timedOut: false
    property bool completed: false
    onRunningChanged: if (!running && !completed) Qt.callLater(function() {
        if (!reader.running && !reader.completed) reader.failed("后端程序无法启动，请检查依赖与配套路径。")
    })
    signal result(string json)
    signal failed(string message)
    onStarted: { output = ""; errorOutput = ""; timedOut = false; completed = false; deadline.restart() }
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: reader.output = text }
    stderr: StdioCollector { waitForEnd: true; onStreamFinished: reader.errorOutput = text }
    onExited: function(code) {
        completed = true; deadline.stop(); killer.stop()
        Qt.callLater(function() {
            if (timedOut) { failed("读取超时，请重试。"); return }
            if (code !== 0) { failed(errorOutput.trim() || "读取失败（退出码 " + code + "）。"); return }
            try {
                var value = JSON.parse(output)
                if (value && value.error) { failed(String(value.error)); return }
                result(output)
            } catch(e) { failed("后端返回了无效数据，请检查配套版本。"); }
        })
    }
    property Timer deadline: Timer {
        interval: 12000
        onTriggered: { reader.timedOut = true; reader.signal(15); reader.killer.restart() }
    }
    property Timer killer: Timer { interval: 1000; onTriggered: if (reader.running) reader.signal(9) }
}
