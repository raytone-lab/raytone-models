import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."
import "components"
import "pages"

Rectangle {
    id: view
    property var backend
    property int current: 0
    property bool homeAvailable: false
    property bool showAdvanced: false
    signal returnHome()
    signal openSettings()
    signal openFiles()
    color: Theme.background
    readonly property var pages: [
        {label:"配方",icon:"recipes",keys:["recipes","instances"],empty:"暂无可用配方。签名未通过的配方不会显示为可运行。"},
        {label:"本地模型",icon:"models",keys:["models","ollamaModels","downloads"],empty:"模型库为空。可在“发现”中查找，或下载配方所需文件。"},
        {label:"发现",icon:"discover",keys:["stats"],empty:"没有匹配的模型。可修改关键词或筛选条件重试。"},
        {label:"运行中",icon:"running",keys:["instances","stats"],empty:"当前没有运行中的模型。启动前请核对设备、模型文件及引擎。"},
        {label:"对话",icon:"chat",keys:["instances"],empty:"暂无就绪的对话模型。输入草稿会保留，可在模型就绪后发送。"},
        {label:"视频",icon:"video",keys:["instances"],empty:"暂无就绪的视频实例。请先核对适用配方与推理环境。"},
        {label:"智能体",icon:"agents",keys:["agents","instances"],empty:"未发现支持的智能体。安装或恢复连接后请重试。"},
        {label:"引擎",icon:"engines",keys:["engines"],empty:"暂无引擎配置，请联系管理员完成本机适配。"}]
    readonly property var selected: pages[current]
    function openPage(page) {
        if (["models", "running", "chat"].indexOf(page) < 0) return ""
        current = pages.findIndex(function (entry) { return entry.icon === page })
        return page
    }
    component PageItem: NavItem {
        required property int modelData
        objectName: "models-nav-" + modelData
        label: view.pages[modelData].label
        current: view.current === modelData
        iconSource: Qt.resolvedUrl("icons/" + view.pages[modelData].icon + "-" + (Theme.dark ? "dark" : "light") + ".svg")
        onClicked: view.current = modelData
    }
    function stateForPage() {
        var counts=[backend.recipes.length,backend.models.length+backend.ollamaModels.length,
                    backend.searchAttempted?backend.searchResults.length:1,backend.instances.length,
                    backend.instances.filter(function(i){return i.ready && i.chat!==false}).length,
                    backend.instances.filter(function(i){return i.ready && i.role==="video"}).length,
                    backend.agents.length,backend.engines.length]
        var keys=current===2 && backend.searchAttempted?["stats","search"]:selected.keys
        return backend.pageState?backend.pageState(keys.concat(["connection"]),counts[current],selected.empty):({phase:"ready",message:""})
    }
    readonly property var pageStatus: stateForPage()

    component RailButton: Button {
        id: shortcut
        required property string label
        required property string iconName
        property bool selected: false
        Layout.fillWidth: true
        implicitHeight: 44
        hoverEnabled: true
        Accessible.name: label
        ToolTip.visible: hovered
        ToolTip.text: label
        contentItem: Item {
            Image {
                anchors.centerIn: parent
                width: 18; height: 18
                source: Qt.resolvedUrl("icons/" + shortcut.iconName + "-" + (Theme.dark ? "dark" : "light") + ".svg")
            }
        }
        background: Rectangle {
            radius: 7
            color: shortcut.selected ? Theme.selection : shortcut.hovered ? Theme.hover : "transparent"
            border.width: shortcut.visualFocus ? 2 : 0
            border.color: Theme.focus
        }
    }
    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: Theme.metrics.rail_width
            Layout.fillHeight: true
            color: Theme.rail
            ColumnLayout {
                anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                anchors.topMargin: 16; anchors.leftMargin: 6; anchors.rightMargin: 6
                spacing: 2
                RailButton { label: "返回首页"; iconName: "home"; visible: view.homeAvailable; onClicked: view.returnHome() }
                RailButton { label: "本地 AI"; iconName: "chat"; selected: true; onClicked: view.openPage("models") }
                RailButton { label: "系统设置"; iconName: "engines"; visible: view.homeAvailable; onClicked: view.openSettings() }
                RailButton { label: "文件"; iconName: "files"; visible: view.homeAvailable; onClicked: view.openFiles() }
            }
            Rectangle { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right; width: 1; color: Theme.border }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Theme.tokens.desktop.toolbar_height
                color: Theme.toolbar
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 22; anchors.verticalCenter: parent.verticalCenter
                    text: "本地 AI"; color: Theme.text; font.family: Theme.font
                    font.pixelSize: Theme.metrics.toolbar_label; font.weight: Font.DemiBold
                }
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.border }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                spacing: 0
                Rectangle {
                    Layout.preferredWidth: view.width <= 620 ? 160 : view.width <= 850 ? 174 : Theme.metrics.sidebar_width
                    Layout.fillHeight: true
                    color: Theme.rail
                    Rectangle { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right; width: 1; color: Theme.border }
                    Flickable {
                        id: rail
                        anchors.fill: parent
                        anchors.topMargin: 16; anchors.bottomMargin: 16; anchors.leftMargin: 10; anchors.rightMargin: 10
                        contentWidth: width
                        contentHeight: railContent.height
                        clip: true
                        ScrollBar.vertical: ScrollBar {}
                        ColumnLayout {
                            id: railContent
                            width: rail.width - (rail.contentHeight > rail.height ? 8 : 0)
                            height: Math.max(implicitHeight, rail.height)
                            spacing: 3
                            Text { text: "常用"; color: Theme.muted; font.family: Theme.font; font.pixelSize: 10; font.weight: Font.DemiBold; Layout.leftMargin: 8; Layout.topMargin: 8; Layout.bottomMargin: 4 }
                            Repeater { model: [4,1,3,2,5]; delegate: PageItem {} }
                            RButton {
                                text: view.showAdvanced ? "收起高级工具" : "高级工具"
                                Layout.topMargin: 8
                                Layout.fillWidth: true
                                onClicked: view.showAdvanced = !view.showAdvanced
                            }
                            Repeater { model: [0,6,7]; delegate: PageItem { visible: view.showAdvanced } }
                            Item { Layout.fillHeight: true; Layout.minimumHeight: 4 }
                            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                            Text {
                                textFormat: Text.PlainText
                                text: view.backend.connection && view.backend.connection.device ? view.backend.connection.device.name : "设备状态读取中"
                                color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption
                                wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.topMargin: 8
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.minimumHeight: 0
                    Layout.topMargin: view.width <= 620 ? 18 : view.width <= 850 ? 22 : 28
                    Layout.leftMargin: view.width <= 620 ? 14 : view.width <= 850 ? 20 : 30
                    Layout.rightMargin: Layout.leftMargin
                    Layout.bottomMargin: 20
                    spacing: 12
                    StackLayout {
                        Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;Layout.minimumWidth:0
                        currentIndex:view.current
                        RecipesPage { backend:view.backend;Layout.minimumHeight:0;Layout.minimumWidth:0 }
                        ModelsPage {
                            backend: view.backend; Layout.minimumHeight: 0; Layout.minimumWidth: 0
                            onOpenDiscover: view.current = 2
                        }
                        DiscoverPage { backend:view.backend;Layout.minimumHeight:0;Layout.minimumWidth:0 }
                        RunningPage {
                            backend: view.backend; Layout.minimumHeight: 0; Layout.minimumWidth: 0
                            onOpenChat: view.openPage("chat")
                        }
                        ChatPage {
                            backend: view.backend; Layout.minimumHeight: 0; Layout.minimumWidth: 0
                            onOpenModels: view.openPage("models")
                        }
                        VideoPage { backend:view.backend;Layout.minimumHeight:0;Layout.minimumWidth:0 }
                        AgentsPage { backend:view.backend;Layout.minimumHeight:0;Layout.minimumWidth:0 }
                        EnginesPage { backend:view.backend;Layout.minimumHeight:0;Layout.minimumWidth:0 }
                    }
                    PageState {
                        Layout.fillWidth:true
                        phase:view.pageStatus.phase
                        message:view.pageStatus.message
                        busy:view.backend.busy!==""
                        onRetry: view.current===2 && view.backend.readErrors.search ? view.backend.retrySearch() : view.backend.refresh()
                    }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth:true;wrapMode:Text.Wrap
                        visible:!!view.backend.connectionMessage
                        text:view.backend.connectionMessage||""
                        color:Theme.muted;font.family:Theme.font;font.pixelSize:Theme.sizeCaption
                    }
                }
            }
        }
    }
    Toast {
        anchors.right:parent.right;anchors.bottom:parent.bottom;anchors.margins:20
        message:view.backend.lastError||view.backend.notice;error:view.backend.lastError!==""
        onDismissed:{view.backend.lastError="";view.backend.notice=""}
    }
}
