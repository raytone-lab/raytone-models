import QtQuick
import ".."

// A state as text and glyph, never by colour alone: neutral, ready, pending, error.
Rectangle {
    id: pill
    property string text: ""
    property string kind: "neutral"
    readonly property string glyph: kind === "ready" ? "✓ " : kind === "pending" ? "↓ " : kind === "error" ? "! " : ""
    implicitWidth: label.implicitWidth + 18
    implicitHeight: label.implicitHeight + 8
    radius: height / 2
    color: kind === "ready" ? Theme.readyFill : kind === "pending" ? Theme.pendingFill
         : kind === "error" ? Theme.errorFill : Theme.raised
    Text {
        id: label
        anchors.centerIn: parent
        text: pill.glyph + pill.text
        color: pill.kind === "ready" ? Theme.readyText : pill.kind === "pending" ? Theme.pendingText
             : pill.kind === "error" ? Theme.errorText : Theme.muted
        font.family: Theme.font
        font.pixelSize: Theme.sizeCaption
        font.weight: Font.DemiBold
    }
}
