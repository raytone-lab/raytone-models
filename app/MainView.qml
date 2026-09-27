import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
import "components"
import "pages"

// The window's content: the navigation rail and the current page.
Rectangle {
    id: view
    property var backend
    property int current: 0
    color: Theme.background
    readonly property var pages: [
        { label: "Recipes", icon: "recipes" }, { label: "Local models", icon: "models" }, { label: "Discover", icon: "discover" },
        { label: "Running", icon: "running" }, { label: "Chat", icon: "chat" }, { label: "Video", icon: "video" },
        { label: "Agents", icon: "agents" }, { label: "Engines", icon: "engines" }]

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 196
            Layout.fillHeight: true
            color: Theme.rail
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border; opacity: 0.6 }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                anchors.topMargin: 24
                spacing: 7
                Image {
                    source: Theme.dark ? Theme.logoOnDark : Theme.logoOnLight
                    sourceSize.width: 140
                    fillMode: Image.PreserveAspectFit
                    Layout.preferredWidth: 140
                    Layout.leftMargin: 10
                    Accessible.name: "Raytone"
                }
                Text { text: "AI LAB / MODELS"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 2.6; Layout.leftMargin: 12; Layout.bottomMargin: 22; Layout.topMargin: 4 }
                Repeater {
                    model: view.pages
                    delegate: NavItem {
                        required property var modelData
                        required property int index
                        label: modelData.label
                        current: view.current === index
                        icon: Qt.resolvedUrl("icons/" + modelData.icon + "-" + (current ? "active" : (Theme.dark ? "dark" : "light")) + ".svg")
                        onClicked: view.current = index
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border; opacity: 0.6 }
                Text { text: "LOCAL WORKSPACE"; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeDense; font.letterSpacing: 1.2; Layout.topMargin: 8 }
                Text { text: "Jetson AGX Thor"; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeBody; font.weight: Font.Bold }
                Text {
                    text: view.backend.stats ? Math.round(view.backend.stats.memory.total / 1073741824) + " GiB unified memory" : "Unified memory"
                    color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption
                }
            }
        }
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 28
            Layout.topMargin: 26
            currentIndex: view.current
            RecipesPage { backend: view.backend }
            ModelsPage { backend: view.backend }
            DiscoverPage { backend: view.backend }
            RunningPage { backend: view.backend }
            ChatPage { backend: view.backend }
            VideoPage { backend: view.backend }
            AgentsPage { backend: view.backend }
            EnginesPage { backend: view.backend }
        }
    }

    Toast {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 20
        message: view.backend.lastError || view.backend.notice
        error: view.backend.lastError !== ""
        onDismissed: { view.backend.lastError = ""; view.backend.notice = "" }
    }
}
