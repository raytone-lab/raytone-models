import QtQuick
import ".."
import "../logic.js" as Logic

Rectangle {
    id: track
    property var value: null
    readonly property var ratio: Logic.meterRatio(value)
    implicitHeight: Theme.meterHeight
    radius: height / 2
    color: Theme.raised
    Accessible.role: Accessible.ProgressBar
    Accessible.description: Logic.meterPercent(value)
    Rectangle {
        objectName: "meter-fill"
        width: track.width * (track.ratio ?? 0)
        height: track.height
        radius: Math.min(width, height) / 2
        color: Theme.accent
        visible: width > 0
    }
}
