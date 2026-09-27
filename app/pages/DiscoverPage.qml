import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    property string kind: "all"
    property string selectedRepo: ""
    property string selectedVariant: ""
    readonly property real total: page.backend.stats ? page.backend.stats.memory.total : 0
    readonly property var visibleResults: page.backend.searchResults.filter(function (r) {
        if (page.kind === "llm") return /text-generation|image-text-to-text/.test(r.pipeline) || r.gguf
        return true
    })
    spacing: 16

    function submit() {
        if (query.text.trim() === "") return
        page.selectedRepo = ""
        page.backend.search(query.text.trim(), page.kind === "video" ? "video" : "")
    }

    PageHeader { title: "Discover"; subtitle: "Find a model on Hugging Face and download the variant that fits this machine." }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        TextField {
            id: query
            Layout.fillWidth: true
            implicitHeight: 44
            placeholderText: "Search Hugging Face, e.g. Qwen3.8, Nemotron, Wan"
            placeholderTextColor: Theme.muted
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: Theme.sizeNav
            leftPadding: 18
            background: Rectangle { radius: height / 2; color: Theme.surface; border.color: query.activeFocus ? Theme.focus : Theme.border; border.width: query.activeFocus ? 2 : 1 }
            onAccepted: page.submit()
            Accessible.name: "Search Hugging Face"
        }
        Repeater {
            model: [{ id: "all", label: "All" }, { id: "llm", label: "LLM" }, { id: "video", label: "Video" }]
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: page.kind === modelData.id
                implicitWidth: chip.implicitWidth + 32
                implicitHeight: 32
                radius: 16
                color: on ? Theme.text : Theme.surface
                border.color: Theme.border
                Text { id: chip; anchors.centerIn: parent; text: parent.modelData.label; color: parent.on ? Theme.background : Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeControl; font.weight: Font.DemiBold }
                MouseArea { anchors.fill: parent; onClicked: { page.kind = parent.modelData.id; if (query.text.trim()) page.submit() } }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 16

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusCard
            color: Theme.surface
            border.color: Theme.border
            Text {
                anchors.centerIn: parent
                visible: page.visibleResults.length === 0
                text: page.backend.searching ? "Searching…" : (query.text ? "No models match these filters." : "Search Hugging Face for a model.")
                color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody
            }
            ListView {
                id: results
                anchors.fill: parent
                anchors.margins: 1
                clip: true
                model: page.visibleResults
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: r
                    required property var modelData
                    width: results.width
                    implicitHeight: 70
                    color: page.selectedRepo === modelData.id ? Theme.raised : "transparent"
                    Rectangle { visible: page.selectedRepo === r.modelData.id; width: 3; height: parent.height; color: Theme.accent }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border; opacity: 0.5 }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 6
                        Item { Layout.fillHeight: true }
                        Text { text: r.modelData.id; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.DemiBold; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        RowLayout {
                            spacing: 10
                            Text { text: "↓ " + Number(r.modelData.downloads).toLocaleString(Qt.locale("en_US"), "f", 0); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                            Text { text: r.modelData.gguf ? "GGUF" : (r.modelData.library || "Library not specified"); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                            Pill { text: r.modelData.gated ? "Gated · access required" : "Ungated"; kind: r.modelData.gated ? "pending" : "neutral" }
                        }
                        Item { Layout.fillHeight: true }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: { page.selectedRepo = r.modelData.id; page.selectedVariant = ""; page.backend.openRepo(r.modelData.id) }
                    }
                }
            }
        }

        Rectangle {
            id: detailPane
            Layout.preferredWidth: 344
            Layout.fillHeight: true
            radius: Theme.radiusCard
            color: Theme.surface
            border.color: Theme.border
            readonly property var detail: page.backend.repoDetail
            readonly property var variants: detail ? detail.variants : []
            readonly property string recommended: Logic.recommended(variants, page.total)
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                Text { text: "REPOSITORY DETAILS"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold }
                Text {
                    text: page.selectedRepo || "Pick a result to see its variants."
                    color: page.selectedRepo ? Theme.text : Theme.muted
                    font.family: Theme.font; font.pixelSize: page.selectedRepo ? Theme.sizeCard : Theme.sizeBody; font.weight: Font.Bold
                    wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                }
                Text {
                    visible: detailPane.detail !== null
                    text: detailPane.detail ? Logic.shortRev(detailPane.detail.revision) + " · " + detailPane.variants.length + " variants" : ""
                    color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeCaption
                }
                Text { visible: page.backend.loadingRepo; text: "Resolving files…"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody }
                ListView {
                    id: variantList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 2
                    model: detailPane.variants
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        id: v
                        required property var modelData
                        readonly property string fitState: Logic.fit(modelData.size, page.total)
                        readonly property bool chosen: page.selectedVariant === modelData.name
                        width: variantList.width
                        implicitHeight: 38
                        radius: Theme.radiusOption
                        color: chosen ? Theme.raised : "transparent"
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 8
                            Rectangle { width: 14; height: 14; radius: 7; color: "transparent"; border.color: v.chosen ? Theme.accent : Theme.border; border.width: 2
                                Rectangle { anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: Theme.accent; visible: v.chosen } }
                            Text { text: v.modelData.name; color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeControl; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                            Pill { visible: v.modelData.name === detailPane.recommended; text: "Recommended"; kind: "ready" }
                            Pill { text: v.fitState; kind: v.fitState === "fits" ? "neutral" : v.fitState === "tight" ? "pending" : "error"; visible: v.fitState !== "fits" }
                            Text { text: Logic.gib(v.modelData.size); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeControl }
                        }
                        MouseArea { anchors.fill: parent; onClicked: page.selectedVariant = v.modelData.name }
                    }
                }
                RButton {
                    Layout.fillWidth: true
                    variant: "primary"
                    readonly property var chosen: (detailPane.variants || []).filter(function (x) { return x.name === page.selectedVariant })[0]
                    text: chosen ? "Download · " + Logic.gib(chosen.size) : "Choose a variant"
                    enabled: !!chosen && page.backend.busy === ""
                    onClicked: page.backend.act("download:" + page.selectedRepo,
                                                ["download", page.selectedRepo + "@" + detailPane.detail.revision, "--variant", page.selectedVariant, "--json"],
                                                "Downloading " + page.selectedVariant)
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: tray.implicitHeight + 28
        radius: Theme.radiusCard
        color: Theme.surface
        border.color: Theme.border
        visible: page.backend.downloads.length > 0
        ColumnLayout {
            id: tray
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 14
            spacing: 10
            RowLayout {
                Text { text: "Downloads"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold; Layout.fillWidth: true }
                Text { text: page.backend.downloads.filter(function (d) { return d.state === "running" }).length + " active"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
            }
            GridLayout {
                columns: 2
                columnSpacing: 24
                rowSpacing: 10
                Layout.fillWidth: true
                Repeater {
                    model: page.backend.downloads.slice(-4)
                    delegate: ColumnLayout {
                        id: dl
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        spacing: 4
                        RowLayout {
                            Text { text: dl.modelData.repo; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeControl; font.weight: Font.DemiBold; elide: Text.ElideMiddle; Layout.fillWidth: true }
                            Text { text: dl.modelData.state === "done" ? "Done" : Math.floor(100 * dl.modelData.progress) + "%"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                        }
                        ProgressLine { Layout.fillWidth: true; value: dl.modelData.progress }
                        Text {
                            text: dl.modelData.state + " · " + Logic.gib(dl.modelData.done) + " / " + Logic.gib(dl.modelData.expected)
                            color: dl.modelData.state === "failed" ? Theme.errorText : Theme.muted
                            font.family: Theme.font; font.pixelSize: Theme.sizeCaption
                        }
                    }
                }
            }
        }
    }
}
