import QtQuick
import QtQuick.Layouts
import ".."
Item {
    id: header
    property string title: ""
    property string subtitle: ""
    default property alias trailing: trail.data
    readonly property bool narrow: width<620
    Layout.fillWidth:true
    implicitHeight:narrow?texts.implicitHeight+(trail.implicitWidth?trail.implicitHeight+10:0):Math.max(texts.implicitHeight,trail.implicitHeight)
    ColumnLayout {
        id:texts;spacing:5
        anchors.left:parent.left;anchors.top:parent.top
        width:header.narrow?parent.width:Math.max(0,parent.width-trail.implicitWidth-16)
        Text { Layout.fillWidth:true;text:header.title;textFormat:Text.PlainText;color:Theme.text;font.family:Theme.font;font.pixelSize:Theme.sizeTitle;font.weight:Font.DemiBold;wrapMode:Text.Wrap }
        Text { Layout.fillWidth:true;text:header.subtitle;textFormat:Text.PlainText;color:Theme.muted;font.family:Theme.font;font.pixelSize:Theme.sizeControl;visible:header.subtitle!=="";wrapMode:Text.Wrap }
    }
    Row { id:trail;spacing:8;x:header.narrow?0:header.width-implicitWidth;y:header.narrow?texts.implicitHeight+10:0 }
}
