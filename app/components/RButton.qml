import QtQuick
import QtQuick.Controls
import ".."

// primary: gold / navy text; secondary: surface with border; danger: error text and border.
Button {
    id: control
    property string variant: "secondary"
    property bool dense: false
    implicitHeight: dense ? 30 : 36
    leftPadding: 16
    rightPadding: 16
    font.family: Theme.font
    font.pixelSize: dense ? Theme.sizeControl : Theme.sizeBody
    font.weight: Font.DemiBold
    hoverEnabled: true
    Accessible.name: text

    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.muted
             : control.variant === "primary" ? Theme.accentText
             : control.variant === "danger" ? Theme.errorText : Theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: height / 2
        color: !control.enabled ? Theme.raised
             : control.variant === "primary" ? (control.down ? Qt.darker(Theme.accent, 1.12) : Theme.accent)
             : (control.hovered ? Theme.raised : Theme.surface)
        border.width: control.visualFocus ? 2 : (control.variant === "primary" ? 0 : 1)
        border.color: control.visualFocus ? Theme.focus
                    : control.variant === "danger" ? Theme.errorText : Theme.border
    }
}
