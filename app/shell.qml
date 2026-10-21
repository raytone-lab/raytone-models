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
        // Omarchy's raytone_actions["Close"] is chord("CTRL", "W"), which injects Ctrl+W
        // into the focused app -- and this window handled no keys at all, so SUPER + W did
        // nothing here while SUPER + Q worked (that one closes by window address and needs
        // no cooperation from the app). StandardKey.Close follows the platform instead of
        // hard-coding the chord.
        Shortcut {
            sequence: StandardKey.Close
            onActivated: Qt.quit()
        }
        MainView { anchors.fill: parent; backend: backend }
    }
}
