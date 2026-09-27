import QtQuick
import QtQuick.Layouts
import ".."

// A 14 px card; its children are laid out in a column.
Rectangle {
    id: card
    default property alias content: column.data
    property alias spacing: column.spacing
    property int padding: 20
    property bool highlighted: false
    radius: Theme.radiusCard
    color: highlighted ? Theme.raised : Theme.surface
    border.color: Theme.border
    border.width: 1
    implicitHeight: column.implicitHeight + 2 * padding
    ColumnLayout {
        id: column
        spacing: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: card.padding
    }
}
