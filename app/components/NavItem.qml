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
    implicitHeight: 38
    Accessible.name: label
    padding:10
    background: Rectangle {
        radius:Theme.radiusOption
        color:item.current?Theme.selection:item.hovered?Theme.raised:"transparent"
        border.width:item.visualFocus?2:0;border.color:Theme.focus
    }
    contentItem: RowLayout {
        spacing:10
        Image { source:item.iconSource;sourceSize:Qt.size(18,18);Layout.preferredWidth:18;Layout.preferredHeight:18 }
        Text { textFormat: Text.PlainText; text:item.label;color:item.current?Theme.accent:Theme.text;font.family:Theme.font;font.pixelSize:Theme.sizeNav;font.weight:item.current?Font.DemiBold:Font.Normal;Layout.fillWidth:true }
    }
}
