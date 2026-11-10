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

    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: view.width < 820 ? 148 : 176
            Layout.fillHeight: true; color: Theme.rail
            Flickable {
                id: rail
                anchors.fill: parent
                anchors.margins: 12
                contentWidth: width
                contentHeight: railContent.height
                clip: true
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: railContent
                    width: rail.width - (rail.contentHeight > rail.height ? 8 : 0)
                    height: Math.max(implicitHeight, rail.height)
                    spacing: 4
                    Image {
                        source: Theme.dark ? Theme.logoOnDark : Theme.logoOnLight
                        sourceSize.width: 120;fillMode: Image.PreserveAspectFit
                        Layout.preferredWidth: 120;Layout.preferredHeight: 42
                        Layout.topMargin: 8;Layout.bottomMargin: 8
                        Accessible.name: "模型控制台"
                    }
                    RButton {
                        text: "返回首页"
                        visible: view.homeAvailable
                        Layout.fillWidth: true
                        onClicked: view.returnHome()
                    }
                    Repeater {
                        model: [4,1,3,2,5]
                        delegate: PageItem {}
                    }
                    RButton {
                        text: view.showAdvanced ? "收起高级工具" : "高级工具"
                        Layout.fillWidth: true
                        onClicked: view.showAdvanced = !view.showAdvanced
                    }
                    Repeater {
                        model: [0,6,7]
                        delegate: PageItem { visible: view.showAdvanced }
                    }
                    Item { Layout.fillHeight: true;Layout.minimumHeight: 4 }
                    Rectangle { Layout.fillWidth: true;height:1;color:Theme.border }
                    Text { textFormat: Text.PlainText; text: "当前设备";color:Theme.muted;font.family:Theme.font;font.pixelSize:Theme.sizeCaption;Layout.topMargin:6 }
                    Text { textFormat: Text.PlainText;
                        text: view.backend.connection && view.backend.connection.device ? view.backend.connection.device.name : "设备状态读取中"
                        color:Theme.text;font.family:Theme.font;font.pixelSize:Theme.sizeControl
                        wrapMode:Text.Wrap;Layout.fillWidth:true
                    }
                    Text { textFormat: Text.PlainText;
                        text: view.backend.readErrors && view.backend.readErrors.stats ? "内存状态暂不可读" : view.backend.stats ? Math.round(view.backend.stats.memory.total/1073741824)+" GiB 系统内存" : "内存状态读取中"
                        color:Theme.muted;font.family:Theme.font;font.pixelSize:Theme.sizeCaption;Layout.fillWidth:true;wrapMode:Text.Wrap
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.minimumHeight:0
            Layout.margins:view.width<820?16:24;spacing:12
            PageState {
                Layout.fillWidth:true
                phase:view.pageStatus.phase
                message:view.pageStatus.message
                busy:view.backend.busy!==""
                onRetry: view.current===2 && view.backend.readErrors.search ? view.backend.retrySearch() : view.backend.refresh()
            }
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
            Text { textFormat: Text.PlainText;
                Layout.fillWidth:true;wrapMode:Text.Wrap
                visible:!!view.backend.connectionMessage
                text:view.backend.connectionMessage||""
                color:Theme.muted;font.family:Theme.font;font.pixelSize:Theme.sizeCaption
            }
        }
    }
    Toast {
        anchors.right:parent.right;anchors.bottom:parent.bottom;anchors.margins:20
        message:view.backend.lastError||view.backend.notice;error:view.backend.lastError!==""
        onDismissed:{view.backend.lastError="";view.backend.notice=""}
    }
}
