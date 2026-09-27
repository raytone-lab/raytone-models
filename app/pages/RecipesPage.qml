import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"
import "../logic.js" as Logic

ColumnLayout {
    id: page
    property var backend
    spacing: 18

    PageHeader {
        title: "Recipes"
        subtitle: "Curated by Raytone AI Lab. Models, engines and parameters tested together on this machine."
        Pill {
            text: page.backend.instances.filter(function (i) { return i.ready }).length + " running"
            kind: "ready"
            visible: page.backend.instances.length > 0
        }
    }

    Text {
        visible: page.backend.recipes.length === 0
        text: page.backend.refusedRecipes.length ? "No recipe passed its signature check." : "No recipes available."
        color: Theme.muted
        font.family: Theme.font
        font.pixelSize: Theme.sizeBody
    }

    ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        clip: true
        GridLayout {
            width: parent.width
            columns: 2
            columnSpacing: 16
            rowSpacing: 16
            Repeater {
                model: page.backend.recipes
                delegate: Card {
                    id: card
                    required property var modelData
                    required property int index
                    readonly property string action: Logic.recipeAction(modelData)
                    readonly property bool fetching: page.backend.fetching[modelData.id] === true
                    Layout.fillWidth: true
                    Layout.columnSpan: index === 0 ? 2 : 1
                    Layout.preferredWidth: 1
                    highlighted: modelData.running
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "RAYTONE AI LAB · SIGNED RECIPE"
                            color: Theme.muted
                            font.family: Theme.font
                            font.pixelSize: Theme.sizeDense
                            font.letterSpacing: 1.4
                            font.weight: Font.Bold
                            Layout.fillWidth: true
                        }
                        Pill {
                            text: card.modelData.running ? "Running" : card.fetching ? "Downloading…"
                                : card.action === "conflict" ? "Conflict" : card.modelData.state === "ready" ? "Ready" : "Not downloaded"
                            kind: card.modelData.running || card.modelData.state === "ready" && card.action !== "conflict" ? "ready"
                                : card.fetching ? "pending" : card.action === "conflict" ? "error" : "neutral"
                        }
                    }
                    Text {
                        text: card.modelData.title
                        color: Theme.text
                        font.family: Theme.font
                        font.pixelSize: card.index === 0 ? Theme.sizeFeatured : Theme.sizeCard
                        font.weight: Font.Bold
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    Text {
                        text: card.modelData.description || ""
                        visible: text !== "" && card.index === 0
                        color: Theme.muted
                        font.family: Theme.font
                        font.pixelSize: Theme.sizeBody
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 18
                        Text {
                            text: (card.modelData.components || []).map(function (c) { return c.served_name + " / " + c.role }).join("  +  ")
                            color: Theme.text
                            font.family: Theme.mono
                            font.pixelSize: Theme.sizeControl
                        }
                        Text { text: "<b>" + card.modelData.memory_gib + " GiB</b> memory"; textFormat: Text.StyledText; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeBody }
                        Text { text: "<b>" + card.modelData.disk_gib + " GiB</b> disk"; textFormat: Text.StyledText; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeBody }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: card.action === "conflict"
                                ? "Another instance serves " + card.modelData.conflicts.join(", ") + ". Stop it on Running, then apply."
                                : (card.modelData.source || "")
                            color: card.action === "conflict" ? Theme.errorText : Theme.muted
                            font.family: Theme.font
                            font.pixelSize: Theme.sizeCaption
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        RButton {
                            variant: card.action === "stop" ? "danger" : "primary"
                            text: card.action === "stop" ? (page.backend.busy === "recipe:" + card.modelData.id ? "Stopping…" : "Stop")
                                : card.action === "apply" ? (page.backend.busy === "recipe:" + card.modelData.id ? "Starting…" : "Apply")
                                : card.action === "conflict" ? "Apply" : (card.fetching ? "Downloading…" : "Download")
                            enabled: page.backend.busy === "" && !card.fetching && card.action !== "conflict"
                            onClicked: {
                                if (card.action === "download") page.backend.fetchRecipe(card.modelData.id)
                                else page.backend.act("recipe:" + card.modelData.id,
                                                      ["recipe", card.action, card.modelData.id, "--json"],
                                                      card.action === "apply" ? "Starting " + card.modelData.title : "Stopped")
                            }
                        }
                    }
                }
            }
        }
    }
}
