import QtQuick
import QtQuick.Controls
import ".."

// The theme's select: a pill like the buttons, a surface popup.
ComboBox {
    id: box
    implicitHeight: 36
    font.family: Theme.font
    font.pixelSize: Theme.sizeControl
    contentItem: Text {
        leftPadding: 16
        rightPadding: 30
        text: box.displayText
        color: box.enabled ? Theme.text : Theme.muted
        font: box.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: box.width - width - 14
        y: (box.height - height) / 2
        text: "▾"
        color: Theme.muted
        font.pixelSize: 12
    }
    background: Rectangle {
        radius: height / 2
        color: box.hovered ? Theme.raised : Theme.surface
        border.color: box.visualFocus ? Theme.focus : Theme.border
        border.width: box.visualFocus ? 2 : 1
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: box.width
        contentItem: Text { text: modelData; color: Theme.text; font: box.font; elide: Text.ElideRight }
        background: Rectangle { color: highlighted ? Theme.raised : Theme.surface; radius: Theme.radiusOption }
        highlighted: box.highlightedIndex === index
    }
    popup: Popup {
        y: box.height + 4
        width: box.width
        padding: 4
        contentItem: ListView { implicitHeight: contentHeight; model: box.popup.visible ? box.delegateModel : null; clip: true }
        background: Rectangle { radius: Theme.radiusCallout; color: Theme.surface; border.color: Theme.border }
    }
}
