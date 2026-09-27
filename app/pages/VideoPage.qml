import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt.labs.folderlistmodel
import Quickshell
import ".."
import "../components"
import "../logic.js" as Logic

// Text to video with MiniMax H3 on the local ComfyUI instance; videos land in ~/Videos/Raytone.
ColumnLayout {
    id: page
    property var backend
    property bool generating: false
    property string status: ""
    property bool failed: false
    property string lastVideo: ""
    property real started: 0
    readonly property var videoModels: page.backend.instances.filter(function (i) { return i.engine === "comfyui" && i.ready })
    readonly property string folder: Quickshell.env("HOME") + "/Videos/Raytone"
    spacing: 14

    function generate() {
        var text = prompt.text.trim()
        if (!text || generating || !videoModels.length) return
        generating = true
        failed = false
        lastVideo = ""
        started = Date.now()
        status = "Queued"
        page.backend.video(text, size.currentText, seconds.currentIndex === 0 ? 5 : 10, turbo.checked)
    }

    Timer {
        interval: 1000; repeat: true; running: page.generating
        onTriggered: page.status = "Generating · " + Logic.clock((Date.now() - page.started) / 1000) + " elapsed"
    }

    Connections {
        target: page.backend
        function onVideoDone(path, secs) {
            page.generating = false
            page.lastVideo = path
            page.status = "Done in " + Logic.clock(secs) + " · " + path.split("/").pop()
        }
        function onVideoError(message) { page.generating = false; page.failed = true; page.status = message }
        function onVideoEnded() { page.generating = false }
    }

    PageHeader {
        title: "Video"
        subtitle: "Text to video with sound, generated on this machine."
        Pill { text: "MiniMax H3"; kind: page.videoModels.length ? "ready" : "neutral" }
    }

    Card {
        Layout.fillWidth: true
        visible: page.videoModels.length === 0
        Text {
            text: "No video model is running. Start the MiniMax H3 recipe on Recipes; it takes a few minutes to load."
            color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; wrapMode: Text.Wrap; Layout.fillWidth: true
        }
    }

    Card {
        Layout.fillWidth: true
        spacing: 12
        Text { text: "DESCRIBE THE VIDEO"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.weight: Font.Bold; font.letterSpacing: 1.4 }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 130
            radius: Theme.radiusCallout
            color: Theme.background
            border.color: prompt.activeFocus ? Theme.focus : Theme.border
            border.width: prompt.activeFocus ? 2 : 1
            ScrollView {
                anchors.fill: parent
                anchors.margins: 10
                TextArea {
                    id: prompt
                    placeholderText: "The scene, the shots and the camera, then the sound: dialogue, effects, music."
                    placeholderTextColor: Theme.muted
                    color: Theme.text
                    font.family: Theme.font
                    font.pixelSize: Theme.sizeNav
                    wrapMode: TextArea.Wrap
                    background: null
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            // 768p held the SoC near 89 C and peaked at 96 C on the Thor, past the thermal guard's
            // 95 C, which rebooted it: 480p only until the fan curve is settled (docs/evidence/p4-video.md)
            RComboBox { id: size; model: ["480p"]; implicitWidth: 110 }
            RComboBox { id: seconds; model: ["5 s", "10 s"]; implicitWidth: 100 }
            CheckBox {
                id: turbo
                checked: true
                leftPadding: 4
                indicator: Rectangle {
                    x: turbo.leftPadding
                    y: (turbo.height - height) / 2
                    width: 16; height: 16; radius: 4
                    color: turbo.checked ? Theme.accent : "transparent"
                    border.color: turbo.checked ? Theme.accent : Theme.border
                    Text { anchors.centerIn: parent; text: "✓"; visible: turbo.checked; color: Theme.accentText; font.pixelSize: 11; font.weight: Font.Bold }
                }
                contentItem: Text {
                    text: "Turbo (8 steps)"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeControl
                    leftPadding: turbo.indicator.width + 8; verticalAlignment: Text.AlignVCenter
                }
            }
            Item { Layout.fillWidth: true }
            RButton {
                variant: page.generating ? "danger" : "primary"
                text: page.generating ? "Stop" : "Generate"
                enabled: page.generating || (prompt.text.trim() !== "" && page.videoModels.length > 0)
                onClicked: page.generating ? page.backend.stopVideo() : page.generate()
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: page.status !== ""
            Text {
                text: page.status
                color: page.failed ? Theme.errorText : Theme.muted
                font.family: Theme.font; font.pixelSize: Theme.sizeBody; wrapMode: Text.Wrap; Layout.fillWidth: true
            }
            RButton { text: "Open"; dense: true; visible: page.lastVideo !== ""; onClicked: page.backend.open(page.lastVideo) }
        }
    }

    Card {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Text { text: "RECENT VIDEOS"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.weight: Font.Bold; font.letterSpacing: 1.4 }
        Text {
            visible: files.count === 0
            text: "Videos you generate are saved in ~/Videos/Raytone."
            color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody
        }
        Repeater {
            model: FolderListModel {
                id: files
                folder: "file://" + page.folder
                nameFilters: ["*.mp4", "*.webm", "*.mkv"]
                sortField: FolderListModel.Time
                showDirs: false
            }
            delegate: RowLayout {
                required property string fileName
                required property string filePath
                required property int fileSize
                required property int index
                visible: index < 5
                Layout.fillWidth: true
                Text { text: fileName; color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeControl; elide: Text.ElideMiddle; Layout.fillWidth: true }
                Text { text: Math.round(fileSize / 1048576 * 10) / 10 + " MiB"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                RButton { text: "Open"; dense: true; onClicked: page.backend.open(filePath) }
            }
        }
    }

    Text {
        text: "Video model: MiniMax H3 by MiniMax, open weights (Comfy-Org's repackage), run locally with ComfyUI."
        color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; wrapMode: Text.Wrap; Layout.fillWidth: true
    }
}
