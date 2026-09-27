import QtQuick
import Quickshell
import "app/logic.js" as Logic

// app/logic.js in Quickshell's own JavaScript engine (node is not QML: no "s" regex flag there,
// for one). Prints PROBE lines and quits; run with tests/ui/logic-probe.
ShellRoot {
    Component.onCompleted: {
        var cases = [["x-Q8_0.gguf", "*Q8_0*"], ["x-Q8_0.gguf", "x-Q[!9-0]_0.gguf"], ["dir/x.gguf", "dir/"], ["x-Q4_K_M.gguf", "x-Q?_K_M.gguf"], ["a\nb.gguf", "a?b.gguf"]]
        console.log("PROBE " + JSON.stringify(cases.map(function (c) { return Logic.includeMatch(c[0], c[1]) })))
        console.log("PROBE " + JSON.stringify(Logic.ggufFiles({ files: ["x-Q4_K_M.gguf", "x-Q8_0.gguf", "mmproj-F16.gguf"], download: { include: ["*Q8_0*"] } })))
        Qt.quit()
    }
}
