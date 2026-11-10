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

    PageHeader { title: "发现"; subtitle: "在 Hugging Face 查找模型。下载前核对容量，运行支持需另行确认。" }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 8
        TextField {
            id: query
            objectName: "discoverQuery"
            Layout.fillWidth: true
            implicitHeight: 44
            placeholderText: "搜索模型，例如 Qwen、Nemotron、Wan"
            placeholderTextColor: Theme.muted
            color: Theme.text
            font.family: Theme.font
            font.pixelSize: Theme.sizeNav
            leftPadding: 18
            background: Rectangle { radius: height / 2; color: Theme.surface; border.color: query.activeFocus ? Theme.focus : Theme.border; border.width: query.activeFocus ? 2 : 1 }
            onAccepted: page.submit()
            Accessible.name: "搜索 Hugging Face"
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: [{ id: "all", label: "全部" }, { id: "llm", label: "语言模型" }, { id: "video", label: "视频" }]
                delegate: RButton {
                    required property var modelData
                    dense: true
                    text: modelData.label
                    variant: page.kind === modelData.id ? "primary" : "secondary"
                    onClicked: { page.kind = modelData.id; if (query.text.trim()) page.submit() }
                }
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        columns: width<620 ? 1 : 2
        columnSpacing:16;rowSpacing:12

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.minimumHeight: 0
            Layout.preferredWidth: parent.columns === 1 ? parent.width : Math.max(240, parent.width - 360)
            Layout.preferredHeight: 240
            radius: Theme.radiusCard
            color: Theme.surface
            border.color: Theme.border
            Text { textFormat: Text.PlainText;
                anchors.centerIn: parent
                width: parent.width - 32
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                visible: page.visibleResults.length === 0
                text: page.backend.searching ? "正在搜索…" : (query.text ? "没有符合筛选条件的模型。" : "输入关键词搜索 Hugging Face。")
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
                        Text { textFormat: Text.PlainText; text: r.modelData.id; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.DemiBold; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        RowLayout {
                            spacing: 10
                            Text { textFormat: Text.PlainText; text: "↓ " + Number(r.modelData.downloads).toLocaleString(Qt.locale("en_US"), "f", 0); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                            Text { textFormat: Text.PlainText; text: r.modelData.gguf ? "GGUF" : (r.modelData.library || "未标注库"); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                            Pill { text: r.modelData.gated ? "需访问授权" : "无需访问授权"; kind: r.modelData.gated ? "pending" : "neutral" }
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
            Layout.preferredWidth: parent.columns === 1 ? parent.width : 344
            Layout.maximumWidth: parent.columns === 1 ? Infinity : 344
            Layout.minimumWidth: 0
            Layout.minimumHeight: 0
            Layout.preferredHeight: 220
            Layout.fillWidth: true
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
                Text { textFormat: Text.PlainText; text: "仓库详情"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.4; font.weight: Font.Bold }
                Text { textFormat: Text.PlainText;
                    text: page.selectedRepo || "选择结果以查看文件版本。"
                    color: page.selectedRepo ? Theme.text : Theme.muted
                    font.family: Theme.font; font.pixelSize: page.selectedRepo ? Theme.sizeCard : Theme.sizeBody; font.weight: Font.Bold
                    wrapMode: Text.WrapAnywhere; Layout.fillWidth: true
                }
                Text { textFormat: Text.PlainText;
                    visible: detailPane.detail !== null
                    text: detailPane.detail ? Logic.shortRev(detailPane.detail.revision) + " · " + detailPane.variants.length + " 个版本" : ""
                    color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeCaption
                }
                PageState {
                    Layout.fillWidth:true
                    phase:page.backend.readErrors && page.backend.readErrors.repo ? "error" : page.backend.loadingRepo ? "loading" : "ready"
                    message:page.backend.readErrors && page.backend.readErrors.repo ? page.backend.readErrors.repo : "正在读取文件列表…"
                    onRetry:page.backend.openRepo(page.selectedRepo)
                }
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
                            Text { textFormat: Text.PlainText; text: v.modelData.name; color: Theme.text; font.family: Theme.mono; font.pixelSize: Theme.sizeControl; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                            Pill { visible: v.modelData.name === detailPane.recommended; text: "容量建议"; kind: "ready" }
                            Pill { text: v.fitState; kind: v.fitState === "fits" ? "neutral" : v.fitState === "tight" ? "pending" : "error"; visible: v.fitState !== "fits" }
                            Text { textFormat: Text.PlainText; text: Logic.gib(v.modelData.size); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeControl }
                        }
                        MouseArea { anchors.fill: parent; onClicked: page.selectedVariant = v.modelData.name }
                    }
                }
                RButton {
                    Layout.fillWidth: true
                    variant: "primary"
                    readonly property var chosen: (detailPane.variants || []).filter(function (x) { return x.name === page.selectedVariant })[0]
                    text: chosen ? "下载 · " + Logic.gib(chosen.size) : "请选择文件版本"
                    enabled: !!chosen && page.backend.busy === ""
                    onClicked: page.backend.act("download:" + page.selectedRepo,
                                                ["download", page.selectedRepo + "@" + detailPane.detail.revision, "--variant", page.selectedVariant, "--json"],
                                                "正在下载 " + page.selectedVariant)
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
                Text { textFormat: Text.PlainText; text: "下载任务"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.Bold; Layout.fillWidth: true }
                Text { textFormat: Text.PlainText; text: page.backend.downloads.filter(function (d) { return d.state === "running" }).length + " 个进行中"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
            }
            GridLayout {
                columns: width < 480 ? 1 : 2
                columnSpacing: 24
                rowSpacing: 10
                Layout.fillWidth: true
                Repeater {
                    model: page.backend.downloads.slice(-4)
                    delegate: ColumnLayout {
                        id: dl
                        required property var modelData
                        readonly property bool hasTotal: Number.isFinite(modelData.expected) && modelData.expected > 0
                        readonly property var ratio: modelData.state === "done" ? 1 : (hasTotal ? modelData.progress : null)
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        spacing: 4
                        RowLayout {
                            Text { textFormat: Text.PlainText; text: dl.modelData.repo; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeControl; font.weight: Font.DemiBold; elide: Text.ElideMiddle; Layout.fillWidth: true }
                            Text { textFormat: Text.PlainText; text: Logic.meterPercent(dl.ratio); color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption }
                        }
                        ProgressLine { Layout.fillWidth: true; value: dl.ratio; Accessible.name: dl.modelData.repo }
                        Text { textFormat: Text.PlainText;
                            text: (dl.modelData.state === "done" ? "已完成" : dl.modelData.state === "failed" ? "下载失败" : "下载中")
                                + " · " + Logic.meterAmount(dl.modelData.done) + " / " + Logic.meterAmount(dl.hasTotal ? dl.modelData.expected : null)
                            color: dl.modelData.state === "failed" ? Theme.errorText : Theme.muted
                            font.family: Theme.font; font.pixelSize: Theme.sizeCaption
                        }
                    }
                }
            }
        }
    }
}
