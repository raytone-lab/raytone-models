// From RaytoneOS (plugins/raytone.models/Theme.qml): Raytone tokens, following the Omarchy theme mode.
pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: root
    readonly property string home: Quickshell.env("HOME")
    readonly property string currentThemePath: home + "/.local/state/omarchy/current/theme"
    readonly property string currentThemeNamePath: home + "/.local/state/omarchy/current/theme.name"
    readonly property string forcedTheme: Quickshell.env("RAYTONE_THEME_FORCE")
    property bool activeThemeReadable: false
    property bool lightMarkerPresent: true
    property string declaredThemeMode: ""
    readonly property bool detectedLight: !activeThemeReadable || declaredThemeMode === "light" || (declaredThemeMode === "" && lightMarkerPresent)
    readonly property bool dark: forcedTheme === "dark" || (forcedTheme !== "light" && !detectedLight)
    readonly property string fontFamily: "Noto Sans"
    property string iconFontFamily: "monospace"
    readonly property int fontTitle: 20
    readonly property int fontIcon: 20
    readonly property int fontCard: 15
    readonly property int fontLabel: 13
    readonly property int fontState: 12
    readonly property int fontCaption: 11
    readonly property int radiusCard: 18
    readonly property int radiusControl: 10
    readonly property int radiusPill: 999
    readonly property color canvas: dark ? "#182235" : "#F6F8FC"
    readonly property color surface: dark ? "#202D42" : "#FFFFFF"
    readonly property color surfaceTranslucent: dark ? "#EB202D42" : "#EBFFFFFF"
    readonly property color surfaceTinted: dark ? "#2A3A5C" : "#EAF0FF"
    readonly property color text: dark ? "#DCE3EE" : "#202D42"
    readonly property color textMuted: dark ? "#A8B3C5" : "#59677D"
    readonly property color textSecondary: dark ? "#A8B3C5" : "#59677D"
    readonly property color separator: dark ? "#0B111C" : "#DFE7F5"
    readonly property color sliderHandle: dark ? "#FFFFFF" : "#FFFFFF"
    readonly property color sliderTrack: dark ? "#62718A" : "#8291A8"
    readonly property color accent: dark ? "#6F96FF" : "#4B7BFF"
    readonly property color accentInteractive: dark ? "#6F96FF" : "#4B7BFF"
    readonly property color onAccent: dark ? "#101827" : "#101827"
    readonly property color accentSecondary: dark ? "#A98DFF" : "#8D6BFF"
    readonly property color symbolViolet: dark ? "#A98DFF" : "#8B5CF6"
    readonly property color success: dark ? "#52B788" : "#27865B"
    readonly property color warning: dark ? "#E2A84B" : "#B87918"
    readonly property color error: dark ? "#F27A7A" : "#C94A4A"
    readonly property color neutral: dark ? "#8A98AE" : "#8A98AE"
    readonly property color shadow: dark ? "#33FFFFFF" : "#26000000"
    readonly property color shadowSoft: dark ? "#1FFFFFFF" : "#1F000000"
    readonly property color transparent: dark ? "transparent" : "transparent"
    readonly property color darkCanvas: dark ? "#0B111C" : "#0B111C"
    readonly property color black: dark ? "#0B111C" : "#0B111C"
    readonly property color textOnDark: dark ? "#DCE3EE" : "#DCE3EE"
    readonly property color textMutedOnDark: dark ? "#8A98AE" : "#8A98AE"
    readonly property color surfaceTranslucentOnDark: dark ? "#EB202D42" : "#EB202D42"

    function parseDeclaredThemeMode(raw) {
        var legacy = ""
        var lines = String(raw || "").split("\n")
        for (var index = 0; index < lines.length; index++) {
            var match = lines[index].match(/^\s*(mode|theme_type)\s*=\s*["']?(light|dark)["']?/)
            if (!match) continue
            if (match[1] === "mode") return match[2]
            legacy = match[2]
        }
        return legacy
    }

    readonly property FileView themeNameFile: FileView {
        path: root.currentThemeNamePath
        watchChanges: true
        printErrors: false
        onLoaded: {
            root.activeThemeReadable = String(text() || "").trim().length > 0
            root.colorsFile.reload()
            root.lightModeFile.reload()
        }
        onFileChanged: reload()
        onLoadFailed: {
            root.activeThemeReadable = false
            root.lightMarkerPresent = true
        }
    }

    readonly property FileView colorsFile: FileView {
        path: root.currentThemePath + "/colors.toml"
        watchChanges: true
        printErrors: false
        onLoaded: root.declaredThemeMode = root.parseDeclaredThemeMode(text())
        onFileChanged: reload()
        onLoadFailed: root.declaredThemeMode = ""
    }

    readonly property FileView lightModeFile: FileView {
        path: root.currentThemePath + "/light.mode"
        watchChanges: true
        printErrors: false
        onLoaded: root.lightMarkerPresent = true
        onFileChanged: reload()
        onLoadFailed: root.lightMarkerPresent = !root.activeThemeReadable
    }

    readonly property Process fontProcess: Process {
        running: true
        command: ["fc-match", "-f", "%{family[0]}", "monospace"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                var family = String(text || "").trim()
                if (family.length > 0) root.iconFontFamily = family
            }
        }
    }
}
