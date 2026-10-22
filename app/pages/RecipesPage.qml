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
                        // Bounded, like the description and the source line below. A card has to
                        // keep room for its Apply button whatever the recipe says, and these three
                        // are the only unbounded text on it -- the trio's title is 69 characters,
                        // which is three lines on a half-width card. What is cut is on hover, so
                        // the bound costs nothing that cannot be got back.
                        id: titleText
                        text: card.modelData.title
                        color: Theme.text
                        font.family: Theme.font
                        font.pixelSize: card.index === 0 ? Theme.sizeFeatured : Theme.sizeCard
                        font.weight: Font.Bold
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        HoverHandler { id: titleHover }
                        ToolTip.visible: titleHover.hovered && titleText.truncated
                        ToolTip.text: titleText.text
                    }
                    Text {
                        // Only the featured card shows this, and it runs to 917 characters on the
                        // trio -- a wall of text where the card is meant to be a summary.
                        id: descriptionText
                        text: card.modelData.description || ""
                        visible: text !== "" && card.index === 0
                        color: Theme.muted
                        font.family: Theme.font
                        font.pixelSize: Theme.sizeBody
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        HoverHandler { id: descriptionHover }
                        ToolTip.visible: descriptionHover.hovered && descriptionText.truncated
                        ToolTip.text: descriptionText.text
                    }
                    Flow {
                        id: facts
                        // A Flow, not a RowLayout. Card's content column is anchored to both sides
                        // of the card, so the column cannot be widened by what is in it -- what
                        // overflowed was this row: without Layout.fillWidth a RowLayout takes its
                        // implicit width and the layout cannot shrink it below that, and the
                        // component list is the widest thing on a card (monospace, one entry per
                        // component). Nothing here clips, so it simply drew on top of the next
                        // card, and the ScrollView pins contentWidth to availableWidth, so there
                        // was no horizontal scroll to reach it either. Narrowing the window made it
                        // worse rather than better: still nothing could shrink, so the memory and
                        // disk figures went off the edge instead.
                        //
                        // Giving the list Layout.fillWidth also stops the overflow, but then the
                        // two figures keep their implicit widths and the list gets whatever is
                        // left -- a sliver, two or three characters wide on a half-width card. A
                        // Flow instead moves the figures to the next line whole and leaves the list
                        // the full width, which is also the existing look when it all fits.
                        Layout.fillWidth: true
                        spacing: 18
                        Text {
                            // width, not Layout.fillWidth: a Flow positions its children at their
                            // own widths rather than distributing space, so capping it here is what
                            // makes the list wrap instead of overflow. implicitWidth is the
                            // unwrapped width and does not depend on width, so this is not a loop.
                            width: Math.min(implicitWidth, facts.width)
                            text: (card.modelData.components || []).map(function (c) { return c.served_name + " / " + c.role }).join("  +  ")
                            color: Theme.text
                            font.family: Theme.mono
                            font.pixelSize: Theme.sizeControl
                            // Wrap, not WordWrap: it prefers the "  +  " separators and falls back
                            // to breaking inside an entry only when one does not fit at all, which
                            // is the right order but is not a promise that entries stay whole.
                            wrapMode: Text.Wrap
                        }
                        // capped the same way: a Flow does not shrink its children either, so
                        // without this the figures are what hangs over the next card once the row
                        // is narrow enough -- which is the thing this page must not do again
                        Text { width: Math.min(implicitWidth, facts.width); text: "<b>" + card.modelData.memory_gib + " GiB</b> memory"; textFormat: Text.StyledText; wrapMode: Text.Wrap; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeBody }
                        Text { width: Math.min(implicitWidth, facts.width); text: "<b>" + card.modelData.disk_gib + " GiB</b> disk"; textFormat: Text.StyledText; wrapMode: Text.Wrap; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeBody }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            // Shares its row with Apply, and runs to 164 characters, so left to
                            // itself it is what pushes the button off the card.
                            id: sourceText
                            text: card.action === "conflict"
                                ? "Another instance serves " + card.modelData.conflicts.join(", ") + ". Stop it on Running, then apply."
                                : (card.modelData.source || "")
                            color: card.action === "conflict" ? Theme.errorText : Theme.muted
                            font.family: Theme.font
                            font.pixelSize: Theme.sizeCaption
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            HoverHandler { id: sourceHover }
                            ToolTip.visible: sourceHover.hovered && sourceText.truncated
                            ToolTip.text: sourceText.text
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
