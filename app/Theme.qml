pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "VisualTokens.js" as Defaults

QtObject {
    id: root
    readonly property string home: Quickshell.env("HOME")
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || home + "/.config"
    readonly property string dataHome: Quickshell.env("XDG_DATA_HOME") || home + "/.local/share"
    readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || home + "/.local/state"
    readonly property string themeFile: stateHome + "/omarchy/current/theme/colors.toml"
    property var tokens: Defaults.tokens
    property string systemMode: "light"
    property string preferredMode: "system"
    // Test renderers may select a mode without writing any system preferences.
    property string mode: ""
    property bool reducedMotion: false
    property bool solidMaterials: false
    property bool preferenceKnown: false
    property bool systemModeKnown: false
    readonly property bool dark: (mode || (preferredMode === "system" ? systemMode : preferredMode)) === "dark"
    readonly property var palette: dark ? tokens.dark : tokens.light
    readonly property color background: palette.canvas
    readonly property color rail: palette.sidebar
    readonly property color surface: palette.surface
    readonly property color raised: palette.surface_tinted
    readonly property color selection: palette.selection
    readonly property color text: palette.text
    readonly property color muted: palette.text_muted
    readonly property color border: palette.separator
    readonly property color accent: palette.accent
    readonly property color accentText: palette.on_accent
    readonly property color focus: palette.accent
    readonly property color readyText: palette.success
    readonly property color readyFill: surface
    readonly property color pendingText: palette.warning
    readonly property color pendingFill: surface
    readonly property color errorText: palette.error
    readonly property color errorFill: surface
    // Native window and cards use opaque surfaces for both materials; no blur writer.
    readonly property string font: tokens.typography.qml_family
    readonly property string mono: "monospace"
    readonly property int sizeTelemetry: 30
    readonly property int sizeTitle: tokens.typography.title_px
    readonly property int sizeFeatured: 20
    readonly property int sizeCard: 16
    readonly property int sizeNav: 14
    readonly property int sizeBody: tokens.typography.body_px
    readonly property int sizeControl: 13
    readonly property int sizeCaption: 12
    readonly property int sizeDense: 11
    readonly property int radiusCard: tokens.radius.card
    readonly property int radiusCallout: tokens.radius.control
    readonly property int radiusOption: tokens.radius.control
    readonly property var logoOnDark: Qt.resolvedUrl("brand/raytone-lockup-reverse.svg")
    readonly property var logoOnLight: Qt.resolvedUrl("brand/raytone-lockup-color.svg")

    function acceptTokens(raw) {
        try {
            var value=JSON.parse(raw)
            if (value.schema !== 1 || !value.typography || !value.radius) return
            for (var side of ["light","dark"])
                for (var key of Object.keys(Defaults.tokens.light))
                    if (!/^#[0-9a-fA-F]{6}$/.test(value[side][key])) return
            if (typeof value.typography.qml_family !== "string" || value.typography.body_px < 10 || value.typography.body_px > 24) return
            root.tokens=value
        } catch(_) {}
    }
    function acceptPreference(raw) {
        try {
            var value=JSON.parse(raw)
            if(value.version !== 1 || ["system","light","dark"].indexOf(value.mode)<0 || ["full","reduced"].indexOf(value.motion)<0 || ["frost","solid"].indexOf(value.material)<0) return
            root.preferredMode=value.mode;root.reducedMotion=value.motion==="reduced";root.solidMaterials=value.material==="solid";root.preferenceKnown=true
        } catch(_) {} // A failed read keeps the last valid appearance.
    }
    function acceptSystemTheme(raw) {
        var match=String(raw).match(/^\s*(?:mode|theme_type)\s*=\s*["']?(light|dark)["']?\s*$/m)
        if(match) { root.systemMode=match[1];root.systemModeKnown=true }
    }
    readonly property FileView osTokens: FileView {
        path: root.dataHome + "/raytone/product/current/themes/raytone-models.json"
        watchChanges: true; printErrors: false
        onFileChanged: reload()
        onLoaded: root.acceptTokens(text())
    }
    readonly property FileView preferences: FileView {
        path: root.configHome + "/raytone/appearance.json"
        watchChanges: true;printErrors: false
        onFileChanged: reload()
        onLoaded: root.acceptPreference(text())
    }
    readonly property FileView themeView: FileView {
        path: root.themeFile;watchChanges: true;printErrors: false
        onFileChanged: reload()
        onLoaded: root.acceptSystemTheme(text())
    }
    readonly property Timer refresh: Timer {
        interval: 2000;running:true;repeat:true
        onTriggered: { root.preferences.reload();root.themeView.reload();root.osTokens.reload() }
    }
}
