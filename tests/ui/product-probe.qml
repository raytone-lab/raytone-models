import QtQuick
import Quickshell
import "app" as App

ShellRoot {
    id: root
    property int checked: 0
    property int failed: 0
    property var draft: null
    property var query: null
    function check(value) { checked++; if(!value) failed++ }
    function find(item, name) {
        if(item.objectName===name) return item
        var children=item.children||[]
        for(var i=0;i<children.length;i++) { var found=find(children[i],name);if(found)return found }
        return null
    }
    App.Backend { id:backend;cli:Quickshell.env("RAYTONE_PROBE_CLI") }
    FloatingWindow {
        visible:true;implicitWidth:1100;implicitHeight:720
        App.MainView { id:main;anchors.fill:parent;backend:backend }
    }
    Timer {
        interval:700;running:true
        onTriggered: {
            App.Theme.acceptPreference('{"version":1,"mode":"dark","motion":"reduced","material":"solid"}')
            root.check(App.Theme.dark && App.Theme.reducedMotion && App.Theme.solidMaterials)
            App.Theme.acceptPreference('{"version":1,"mode":"invalid"}')
            root.check(App.Theme.dark && App.Theme.reducedMotion)
            App.Theme.acceptSystemTheme('mode = "invalid"')
            App.Theme.acceptTokens('{"schema":1}')
            root.check(String(App.Theme.background)==="#202124")
            backend.loaded={};backend.readErrors={}
            root.check(backend.pageState(["models"],0,"").phase==="loading")
            backend.readFailed("models","Permission denied")
            root.check(backend.pageState(["models"],0,"").phase==="denied")
            backend.readOk("models")
            root.check(backend.pageState(["models"],0,"empty").phase==="empty")
            backend.readList("models",{})
            root.check(backend.pageState(["models"],0,"").phase==="error")
            backend.readList("models",[])
            main.current=4
            root.draft=root.find(main,"chatDraft");root.query=root.find(main,"discoverQuery")
            root.check(root.draft!==null && root.query!==null)
            if(root.draft) { root.draft.text="第二批草稿 nihao 需要保留";root.draft.forceActiveFocus() }
            if(root.query)root.query.text="中文长名称：模型 / 同名模型"
        }
    }
    Timer {
        interval:17500;running:true
        onTriggered: {
            root.check(root.draft && root.draft.text==="第二批草稿 nihao 需要保留")
            root.check(root.query && root.query.text==="中文长名称：模型 / 同名模型")
            root.check(root.draft && root.draft.activeFocus)
            console.log(root.failed===0?"PRODUCT_PROBE_PASS":"PRODUCT_PROBE_FAIL",root.checked,root.failed)
            Qt.quit()
        }
    }
}
