import QtQuick
import QtQuick.Layouts
import ".."

// Title and subtitle on the left, whatever the page puts in it on the right.
Item {
    id: header
    property string title: ""
    property string subtitle: ""
    default property alias trailing: trail.data
    Layout.fillWidth: true
    implicitHeight: Math.max(texts.implicitHeight, trail.implicitHeight)
    ColumnLayout {
        id: texts
        spacing: 4
        anchors.left: parent.left
        anchors.right: trail.left
        anchors.rightMargin: 16
        anchors.top: parent.top
        Text { text: header.title; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeTitle; font.weight: Font.Bold }
        Text { text: header.subtitle; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; visible: header.subtitle !== ""; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
    Row {
        id: trail
        spacing: 8
        anchors.right: parent.right
        anchors.top: parent.top
    }
}
