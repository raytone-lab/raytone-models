import QtQuick
import Quickshell
import "."

// Raytone Models, a Quickshell application: `raytone-models-app` runs `qs -p` on this directory.
ShellRoot {
    Backend { id: backend }
    FloatingWindow {
        id: window
        title: "Raytone Models"
        implicitWidth: 1200
        implicitHeight: 760
        color: Theme.background
        visible: true
        onVisibleChanged: if (!visible) Qt.quit()
        MainView { anchors.fill: parent; backend: backend }
    }
}
