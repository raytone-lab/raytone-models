import QtQuick
import QtQuick.Controls

Button {
    id: control

    property string variant: "secondary"
    property bool emphasized: checked || variant === "primary"
    readonly property color fillColor: !enabled
        ? Theme.surfaceTinted
        : down
            ? (emphasized ? Theme.accentSecondary : Theme.separator)
            : hovered
                ? (emphasized ? Theme.accentSecondary : variant === "outline" ? Theme.surfaceTinted : Theme.surface)
                : emphasized
                    ? Theme.accentInteractive
                    : variant === "outline" ? Theme.transparent : Theme.surfaceTinted

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontLabel
    implicitHeight: 32
    activeFocusOnTab: true
    scale: down ? 0.98 : 1

    contentItem: Text {
        text: control.text
        color: !control.enabled ? Theme.textMuted : control.emphasized ? Theme.onAccent : Theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font: control.font
    }

    background: Rectangle {
        radius: Theme.radiusControl
        color: control.fillColor
        border.color: control.visualFocus ? Theme.accentInteractive : control.hovered ? Theme.textMuted : Theme.separator
        border.width: control.visualFocus ? 2 : 1

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }

    Behavior on scale {
        NumberAnimation { duration: 70 }
    }
}
