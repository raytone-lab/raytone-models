import QtQuick
import QtQuick.Controls
import ".."

ComboBox {
    id: box
    implicitHeight: Theme.metrics.button_height
    font.family: Theme.font
    font.pixelSize: Theme.sizeControl
    contentItem: Text { textFormat: Text.PlainText;
        leftPadding: 16
        rightPadding: 30
        text: box.displayText
        color: box.enabled ? Theme.text : Theme.muted
        font: box.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text { textFormat: Text.PlainText;
        x: box.width - width - 14
        y: (box.height - height) / 2
        text: "▾"
        color: Theme.muted
        font.pixelSize: 12
    }
    background: Rectangle {
        radius: Theme.radiusCallout
        color: box.hovered ? Theme.hover : Theme.toolbar
        border.color: box.visualFocus ? Theme.focus : Theme.border
        border.width: box.visualFocus ? 2 : 1
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: box.width
        contentItem: Text { textFormat: Text.PlainText; text: modelData; color: Theme.text; font: box.font; elide: Text.ElideRight }
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
