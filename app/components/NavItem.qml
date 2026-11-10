import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
Button {
    id: item
    property string label: ""
    property string iconSource: ""
    property bool current: false
    Layout.fillWidth: true
    implicitHeight: Theme.metrics.navigation_height
    Accessible.name: label
    padding:5
    background: Rectangle {
        radius:6
        color:item.current?Theme.selection:item.hovered?Theme.hover:"transparent"
        border.width:item.visualFocus?2:0;border.color:Theme.focus
    }
    contentItem: RowLayout {
        spacing:9
        Rectangle {
            Layout.preferredWidth: 23
            Layout.preferredHeight: 23
            radius: 6
            color: Theme.toolbar
            border.color: Theme.border
            Image { anchors.centerIn: parent; source:item.iconSource; width:16;height:16 }
        }
        Text { textFormat: Text.PlainText; text:item.label;color:Theme.text;font.family:Theme.font;font.pixelSize:Theme.sizeNav;font.weight:item.current?Font.DemiBold:Font.Normal;Layout.fillWidth:true }
    }
}
