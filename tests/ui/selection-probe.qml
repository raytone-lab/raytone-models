import QtQuick
import Quickshell
import "app/pages"

ShellRoot {
    FloatingWindow {
        implicitWidth: 1200; implicitHeight: 738; visible: true
        QtObject {
            id: fixture
            property var instances: [{served_name:"A",ready:true,chat:true,current:false},{served_name:"B",ready:true,chat:true,current:true}]
            signal chatDelta(string text)
            signal chatDone(var value)
            signal chatEnded()
            signal chatError(string text)
            function chat() { throw new Error("Fixture never sends inference") }
        }
        ChatPage { id: page; anchors.fill:parent; backend:fixture }
        Timer {
            property int phase: 0
            property int passed: 0
            interval: 200; repeat:true; running:true
            function find(item) {
                if (item.objectName === "chatModelSelection") return item
                for (var i=0;i<item.children.length;i++) { var found=find(item.children[i]); if (found) return found }
                return null
            }
            onTriggered: {
                var combo=find(page)
                var expected=[1,0,1,1,-1,-1,0,1][phase]
                if (!combo || combo.currentIndex !== expected) {
                    console.log("SELECTION_PROBE_FAIL",phase,combo?combo.currentIndex:"missing",expected);Qt.quit();return
                }
                passed++
                if (phase===0) page.selectedModel="A"
                else if (phase===1) fixture.instances=[fixture.instances[1],fixture.instances[0]]
                else if (phase===2) fixture.instances=fixture.instances.slice()
                else if (phase===3) fixture.instances=[fixture.instances[0]]
                else if (phase===4) fixture.instances=[]
                else if (phase===5) {
                    page.selectedModel=""
                    fixture.instances=[{served_name:"B",ready:true,chat:true,current:true},{served_name:"A",ready:true,chat:true,current:false}]
                } else if (phase===6) fixture.instances=[{served_name:"B",ready:true,chat:true,current:false},{served_name:"A",ready:true,chat:true,current:true}]
                else { console.log("SELECTION_PROBE_PASS",passed,0);Qt.quit() }
                phase++
            }
        }
    }
}
