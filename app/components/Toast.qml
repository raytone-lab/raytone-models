import QtQuick
import ".."

// Bottom-right, nonmodal; notices fade after 4 s, errors stay until dismissed.
Rectangle {
    id: toast
    property string message: ""
    property bool error: false
    signal dismissed()
    visible: message !== ""
    width: Math.min(360, label.implicitWidth + 48)
    height: label.implicitHeight + 28
    radius: Theme.radiusCallout
    color: error ? Theme.errorFill : Theme.surface
    border.color: error ? Theme.errorText : Theme.border
    Text {
        id: label
        anchors.fill: parent
        anchors.margins: 14
        anchors.rightMargin: 30
        text: (toast.error ? "! " : "✓ ") + toast.message
        color: toast.error ? Theme.errorText : Theme.text
        wrapMode: Text.Wrap
        font.family: Theme.font
        font.pixelSize: Theme.sizeBody
    }
    Text {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        text: "×"
        color: Theme.muted
        font.pixelSize: 16
        MouseArea { anchors.fill: parent; anchors.margins: -6; onClicked: toast.dismissed() }
    }
    Timer { running: toast.visible && !toast.error; interval: 4000; onTriggered: toast.dismissed() }
}
