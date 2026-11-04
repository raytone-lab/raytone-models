import QtQuick
import QtQuick.Controls
import Quickshell
import "app" as App

// Real CLI reads; never activates a recipe action or downloads a model.
ShellRoot {
    id: root
    property int checked: 0
    property int failed: 0
    property var scroll: null
    property var grid: null
    property var button: null
    property var card: null
    property string lastId: ""
    property real position: 0
    property int probeWidth: 1200
    property int probeHeight: 738
    function check(value, reason) {
        checked++
        if (!value) { failed++; console.log("RECIPES_CHECK_FAILED", reason) }
    }
    function find(item, name) {
        if (item.objectName === name) return item
        for (var child of item.children || []) { var result = find(child, name); if (result) return result }
        return null
    }
    App.Backend { id: backend; cli: Quickshell.env("RAYTONE_PROBE_CLI") }
    FloatingWindow {
        id: window
        visible: true; implicitWidth: 1200; implicitHeight: 738
        App.MainView { id: view; width: root.probeWidth; height: root.probeHeight; backend: backend }
    }
    Timer {
        interval: 1800; running: true
        onTriggered: {
            root.scroll = root.find(view, "recipesScroll")
            root.grid = root.find(view, "recipesGrid")
            root.check(backend.recipes.length >= 4, "overflow recipes loaded from actual CLI")
            root.lastId = backend.recipes[backend.recipes.length - 1].id
            root.button = root.find(view, "recipeAction-" + root.lastId)
            root.card = root.find(view, "recipeCard-" + root.lastId)
            root.check(root.grid.columns === 2, "wide layout")
            root.check(root.scroll.contentHeight > root.scroll.availableHeight && root.scroll.availableHeight > 0, "bounded overflow viewport")
            root.check(root.scroll.ScrollBar.vertical.height >= root.scroll.availableHeight - 2, "full scrollbar track")
            root.check(root.scroll.ScrollBar.vertical.policy === ScrollBar.AlwaysOn, "overflow scrollbar stays visible")
            root.button.forceActiveFocus()
            root.position = root.scroll.contentItem.contentY
            root.check(root.position > 0, "keyboard focus reveals last action")
        }
    }
    Timer {
        interval: 19000; running: true
        onTriggered: {
            root.check(root.button === root.find(view, "recipeAction-" + root.lastId), "same action after three refresh cycles")
            root.check(root.card === root.find(view, "recipeCard-" + root.lastId), "same card after refresh")
            root.check(root.button.activeFocus, "focus preserved")
            root.check(Math.abs(root.position - root.scroll.contentItem.contentY) < 1, "scroll preserved")
            root.probeWidth = 640; root.probeHeight = 420
        }
    }
    Timer {
        interval: 20000; running: true
        onTriggered: {
            root.check(root.grid.columns === 1, "narrow layout uses one column")
            root.check(root.scroll.availableHeight > 0 && root.scroll.availableHeight < 300, "low viewport remains bounded")
            root.check(root.grid.width <= root.scroll.availableWidth, "no horizontal card overflow")
            root.button.forceActiveFocus()
        }
    }
    Timer {
        interval: 21300; running: true
        onTriggered: backend.recipes = []
    }
    Timer {
        interval: 22000; running: true
        onTriggered: {
            console.log("RECIPES_EMPTY_GEOMETRY", backend.recipes.length, root.grid.implicitHeight, root.scroll.contentHeight, root.scroll.availableHeight)
            root.check(root.scroll.contentHeight === 0, "empty content has no fake range")
            root.check(root.scroll.ScrollBar.vertical.policy === ScrollBar.AlwaysOff, "empty content has no fake bar")
            console.log(root.failed === 0 ? "RECIPES_PROBE_PASS" : "RECIPES_PROBE_FAIL", root.checked, root.failed)
            Qt.quit()
        }
    }
}
