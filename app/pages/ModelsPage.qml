import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    property var pendingDelete: null
    spacing: 18

    function runArgs(m) {
        // conservative settings until a recipe carries the model's own
        var name = Logic.repoName(m.repo).toLowerCase().replace(/[^a-z0-9.:_-]+/g, "-")
        var args = ["start", m.repo + "@" + m.revision, "--engine", "vllm", "--name", name,
                    "--arg", "gpu-memory-utilization=0.6", "--arg", "max-model-len=65536", "--arg", "enable-prefix-caching", "--json"]
        if (/qwen3\.?8/i.test(m.repo))
            args = args.concat(["--arg", "enable-auto-tool-choice", "--arg", "tool-call-parser=qwen3_coder", "--arg", "reasoning-parser=qwen3"])
        return args
    }

    PageHeader {
        title: "Local models"
        subtitle: "Everything in the model store, at the commits you downloaded."
        Pill { text: page.backend.models.length + " models"; kind: "neutral" }
    }

    Text {
        visible: page.backend.models.length === 0
        text: "Your model store is empty. Find a model on Discover, or download a recipe."
        color: Theme.muted
        font.family: Theme.font
        font.pixelSize: Theme.sizeBody
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        radius: Theme.radiusCard
        color: Theme.surface
        border.color: Theme.border
        visible: page.backend.models.length > 0
        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 1
            clip: true
            model: page.backend.models
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                readonly property string state: Logic.modelState(modelData)
                readonly property bool draft: modelData.role === "draft"
                readonly property bool runnable: modelData.format === "safetensors" && state === "ready" && !draft
                width: list.width
                implicitHeight: 64
                color: index % 2 ? "transparent" : Qt.rgba(0, 0, 0, 0)
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border; opacity: 0.5 }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 14
                    spacing: 14
                    ColumnLayout {
                        spacing: 2
                        Layout.fillWidth: true
                        Text { text: Logic.repoName(row.modelData.repo); color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeNav; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                        Text {
                            text: Logic.repoOrg(row.modelData.repo) + " · " + Logic.shortRev(row.modelData.revision)
                            color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeCaption
                        }
                    }
                    Text { text: Logic.gib(row.modelData.size); color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeControl; Layout.preferredWidth: 80; horizontalAlignment: Text.AlignRight }
                    Text { text: row.modelData.format; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeControl; Layout.preferredWidth: 78 }
                    Text { text: row.modelData.quant || "Not specified"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeControl; Layout.preferredWidth: 118; elide: Text.ElideRight }
                    Pill {
                        text: row.draft ? "draft" : row.state
                        kind: row.draft ? "neutral" : row.state === "ready" ? "ready" : row.state === "unverified" ? "neutral" : "pending"
                        Layout.preferredWidth: 110
                    }
                    RButton {
                        dense: true
                        variant: "primary"
                        text: page.backend.busy === "run:" + row.modelData.repo ? "Starting…" : "Run"
                        enabled: row.runnable && page.backend.busy === ""
                        ToolTip.visible: hovered && !row.runnable
                        ToolTip.text: row.draft ? "A speculative-decoding draft: it runs inside a recipe, next to its model"
                                    : row.modelData.format === "gguf" ? "GGUF runs on llama.cpp or Ollama (coming next)"
                                    : row.modelData.format === "diffusion" ? "Video models run through a recipe" : "Not downloaded completely"
                        onClicked: page.backend.act("run:" + row.modelData.repo, page.runArgs(row.modelData), "Starting " + Logic.repoName(row.modelData.repo))
                    }
                    RButton {
                        dense: true
                        variant: "danger"
                        text: "Delete"
                        enabled: page.backend.busy === ""
                        onClicked: { page.pendingDelete = row.modelData; confirm.open() }
                    }
                }
            }
        }
    }

    Dialog {
        id: confirm
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 460
        title: "Delete this model?"
        standardButtons: Dialog.Cancel | Dialog.Ok
        background: Rectangle { radius: Theme.radiusCard; color: Theme.surface; border.color: Theme.border }
        header: Text { text: "Delete this model?"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeCard; font.weight: Font.Bold; padding: 20 }
        contentItem: Text {
            text: page.pendingDelete ? page.pendingDelete.repo + " at " + Logic.shortRev(page.pendingDelete.revision)
                                       + "\n" + Logic.gib(page.pendingDelete.size) + " will be freed. Running instances keep it until they stop."
                                     : ""
            color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; wrapMode: Text.Wrap; padding: 20
        }
        onAccepted: if (page.pendingDelete) page.backend.act("delete:" + page.pendingDelete.repo,
                                                           ["delete", page.pendingDelete.repo, "--json"], "Deleted " + Logic.repoName(page.pendingDelete.repo))
    }
}
