import QtQuick
import Quickshell
import "app" as App

// Renders every page of the app, dark then light, to $RAYTONE_UI_SHOTS/<mode>-<n>.png and quits.
// Run it with tests/ui/render (Quickshell loads modules from inside its config folder only).
ShellRoot {
    FixtureBackend { id: fixture }
    FloatingWindow {
        id: window
        implicitWidth: 1200
        implicitHeight: 760
        visible: true
        color: App.Theme.background
        App.MainView { id: main; anchors.fill: parent; backend: fixture }
    }
    Timer {
        id: shooter
        property int step: 0
        readonly property var modes: ["dark", "light"]
        interval: 900
        running: true
        repeat: true
        onTriggered: {
            var mode = modes[Math.floor(step / 7)]
            if (mode === undefined) { Qt.quit(); return }
            App.Theme.mode = mode
            main.current = step % 7
            var name = mode + "-" + (step % 7)
            running = false
            Qt.callLater(function () {
                main.grabToImage(function (result) {
                    result.saveToFile(Quickshell.env("RAYTONE_UI_SHOTS") + "/" + name + ".png")
                    shooter.step++
                    shooter.running = true
                })
            })
        }
    }
}
