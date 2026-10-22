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
        // Omarchy's raytone_actions["Close"] is chord("CTRL", "W"), which injects Ctrl+W into the
        // focused app -- and this window had no handler for it, so SUPER + W did nothing here
        // while SUPER + Q worked (that one closes by window address and needs no cooperation from
        // the app). StandardKey.Close is asked for rather than the chord spelled out.
        //
        // sequences, plural, on purpose. Qt's keyBindings(Close) returns more than one sequence,
        // and the singular form registers only the first of them and warns that it dropped the
        // rest. Which one ends up first depends on QPlatformTheme's keyboard scheme: the unix
        // themes report X11 and put Ctrl+W there, but the base class defaults to the Windows
        // scheme, which puts Ctrl+F4 first -- so under a platform theme that leaves that hint
        // alone, the singular form would silently bind the wrong key.
        Shortcut {
            sequences: [StandardKey.Close]
            onActivated: Qt.quit()
        }
        MainView { anchors.fill: parent; backend: backend }
    }
}
