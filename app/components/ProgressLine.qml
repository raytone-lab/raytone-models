import QtQuick
import ".."

// 5 px gold bar on a neutral track; the caller always shows the number next to it.
Rectangle {
    property real value: 0
    implicitHeight: 5
    radius: height / 2
    color: Theme.raised
    Accessible.role: Accessible.ProgressBar
    Rectangle {
        width: Math.max(parent.height, parent.width * Math.min(1, Math.max(0, parent.value)))
        height: parent.height
        radius: height / 2
        color: Theme.accent
        visible: parent.value > 0
    }
}
