import QtQuick
import Quickshell
import "app/components"

ShellRoot {
    id: root
    property int completed: 0
    property int failures: 0
    function check(ok) {
        if (!ok) failures++
        completed++
        if (completed === 5) { console.log(failures === 0 ? "READ_PROCESS_PASS 5" : "READ_PROCESS_FAIL", failures); Qt.quit() }
    }
    ReadProcess {
        command: ["/usr/bin/python3", "-c", "print('[]')"]; running: true
        onResult: function(text) { root.check(Array.isArray(JSON.parse(text))) }
        onFailed: root.check(false)
    }
    ReadProcess {
        command: ["/usr/bin/python3", "-c", "print('invalid')"]; running: true
        onResult: root.check(false)
        onFailed: root.check(true)
    }
    ReadProcess {
        command: ["/usr/bin/python3", "-c", "import sys;sys.exit(3)"]; running: true
        onResult: root.check(false)
        onFailed: root.check(true)
    }
    ReadProcess {
        command: ["/nonexistent/raytone-models-cli"]; running: true
        onResult: root.check(false)
        onFailed: root.check(true)
    }
    ReadProcess {
        command: ["/usr/bin/python3", "-c", "import time;time.sleep(30)"]; running: true
        onResult: root.check(false)
        onFailed: function(message) { root.check(timedOut && message.indexOf("超时") >= 0) }
    }
    Timer { interval: 20000; running: true; onTriggered: { console.log("READ_PROCESS_FAIL timeout", root.completed); Qt.quit() } }
}
