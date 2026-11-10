//@ pragma AppId ai.raytone.Models
//@ pragma ShellId ai.raytone.Models
import QtQuick
import Quickshell
import Quickshell.Io
import "."

// Raytone Models, a Quickshell application: `raytone-models-app` runs `qs -p` on this directory.
ShellRoot {
    id: root
    readonly property string homeCommand: Quickshell.env("RAYTONE_MODELS_HOME_COMMAND") || ""
    Backend { id: backend }
    IpcHandler {
        target: "raytone.models"
        function openPage(page: string): string { return view.openPage(page) }
        function currentPage(): string { return view.selected.icon }
    }
    Process {
        id: desktopShortcut
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0 || exitStatus !== 0) backend.lastError = "暂时无法打开该入口，请从桌面顶栏重试。"
        }
    }
    function launchShortcut(args) {
        if (homeCommand === "" || desktopShortcut.running) return
        desktopShortcut.command = [homeCommand].concat(args)
        desktopShortcut.running = true
    }
    FloatingWindow {
        id: window
        title: "模型控制台"
        implicitWidth: Theme.metrics.window_width
        implicitHeight: Theme.metrics.window_height
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
        MainView {
            id: view
            anchors.fill: parent
            backend: backend
            current: 1
            homeAvailable: root.homeCommand !== ""
            onReturnHome: root.launchShortcut(["open"])
            onOpenSettings: root.launchShortcut(["request", '{"action":"common","key":"settings"}'])
            onOpenFiles: root.launchShortcut(["request", '{"action":"common","key":"files"}'])
        }
    }
}
