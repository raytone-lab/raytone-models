import QtQuick
import QtQuick.Layouts
import ".."
Rectangle {
    id: root
    property string phase: "ready"
    property string message: ""
    property bool busy: false
    signal retry()
    visible: phase!=="ready" || busy
    implicitHeight: visible ? row.implicitHeight+24 : 0
    color: Theme.surface;radius:Theme.radiusCallout;border.color:phase==="error"||phase==="denied"?Theme.errorText:Theme.border
    RowLayout {
        id: row
        anchors.fill:parent;anchors.margins:12;spacing:12
        Text {
            Layout.fillWidth:true;wrapMode:Text.Wrap;textFormat:Text.PlainText
            text:(root.busy?"正在处理，请稍候。\n":"")+(root.phase==="error"?"状态读取失败；已加载的列表保留上次结果。\n":root.phase==="denied"?"权限不足或授权已取消。\n":"")+root.message
            color:root.phase==="error"||root.phase==="denied"?Theme.errorText:Theme.muted
            font.family:Theme.font;font.pixelSize:Theme.sizeBody
        }
        RButton { visible:root.phase==="error"||root.phase==="denied";text:"重试";onClicked:root.retry() }
    }
}
