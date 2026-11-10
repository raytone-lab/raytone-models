import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: control
    property string variant: "secondary"
    property bool dense: false
    implicitHeight: Theme.metrics.button_height
    leftPadding: dense ? 9 : 12
    rightPadding: leftPadding
    font.family: Theme.font
    font.pixelSize: Theme.sizeControl
    font.weight: Font.Medium
    hoverEnabled: true
    Accessible.name: text

    contentItem: Text { textFormat: Text.PlainText;
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
        radius: Theme.radiusCallout
        color: !control.enabled ? Theme.raised
             : control.variant === "primary" ? (control.down ? Qt.darker(Theme.accent, 1.12) : Theme.accent)
             : (control.hovered ? Theme.hover : Theme.toolbar)
        border.width: control.visualFocus ? 2 : (control.variant === "primary" ? 0 : 1)
        border.color: control.visualFocus ? Theme.focus
                    : control.variant === "danger" ? Theme.errorText : Theme.border
    }
}
