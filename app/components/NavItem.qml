import QtQuick
import QtQuick.Layouts
import ".."

Rectangle {
    id: item
    property string label: ""
    property string icon: ""
    property bool current: false
    signal clicked()
    Layout.fillWidth: true
    implicitHeight: 43
    radius: height / 2
    color: current ? Theme.accent : (mouse.containsMouse ? Theme.raised : "transparent")
    Accessible.role: Accessible.PageTab
    Accessible.name: label
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        spacing: 12
        Image {
            source: item.icon
            sourceSize: Qt.size(19, 19)
            Layout.preferredWidth: 19
            Layout.preferredHeight: 19
            opacity: 0.95
        }
        Text {
            text: item.label
            color: item.current ? Theme.accentText : Theme.text
            font.family: Theme.font
            font.pixelSize: Theme.sizeNav
            font.weight: item.current ? Font.Bold : Font.DemiBold
            Layout.fillWidth: true
        }
    }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: item.clicked() }
}
