pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

// Raytone Models tokens (design/DESIGN.md), dark or light as the current Omarchy theme declares.
QtObject {
    id: root

    readonly property string themeFile: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    property string mode: "dark"
    readonly property bool dark: mode !== "light"

    readonly property color background: dark ? "#111C32" : "#F6F7FA"
    readonly property color rail: dark ? "#0D172B" : "#EDF0F5"
    readonly property color surface: dark ? "#182649" : "#FFFFFF"
    readonly property color raised: dark ? "#1E3052" : "#F0F3F8"
    readonly property color text: dark ? "#F1F4FA" : "#162547"
    readonly property color muted: dark ? "#AEBBD1" : "#52617A"
    readonly property color border: dark ? "#3D5071" : "#8997AE"
    readonly property color accent: "#DFAE39"
    readonly property color accentText: "#182649"
    readonly property color focus: dark ? "#F2C966" : "#806018"
    readonly property color readyText: dark ? "#9EDBBB" : "#246044"
    readonly property color readyFill: dark ? "#203D39" : "#E6F2EB"
    readonly property color pendingText: dark ? "#F2CE87" : "#765217"
    readonly property color pendingFill: dark ? "#423723" : "#FBEFDA"
    readonly property color errorText: dark ? "#F4B3B8" : "#9E3547"
    readonly property color errorFill: dark ? "#432C3C" : "#FBE9EC"

    // No font download: Inter when installed, then the platform's sans (with its CJK fallback).
    readonly property string font: Qt.fontFamilies().indexOf("Inter") >= 0 ? "Inter"
                                 : (Qt.fontFamilies().indexOf("Noto Sans") >= 0 ? "Noto Sans" : "sans-serif")
    readonly property string mono: Qt.fontFamilies().indexOf("JetBrainsMono Nerd Font") >= 0 ? "JetBrainsMono Nerd Font"
                                 : "monospace"

    readonly property int sizeTelemetry: 36
    readonly property int sizeTitle: 28
    readonly property int sizeFeatured: 22
    readonly property int sizeCard: 18
    readonly property int sizeNav: 14
    readonly property int sizeBody: 13
    readonly property int sizeControl: 12
    readonly property int sizeCaption: 11
    readonly property int sizeDense: 10

    readonly property int radiusCard: 14
    readonly property int radiusCallout: 10
    readonly property int radiusOption: 8

    readonly property var logoOnDark: Qt.resolvedUrl("brand/raytone-lockup-reverse.svg")
    readonly property var logoOnLight: Qt.resolvedUrl("brand/raytone-lockup-color.svg")

    readonly property FileView themeView: FileView {
        path: root.themeFile
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            var m = String(text()).match(/^\s*mode\s*=\s*["']?(light|dark)["']?/m)
            root.mode = m ? m[1] : "dark"
        }
    }
}
