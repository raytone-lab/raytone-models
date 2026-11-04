import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

ColumnLayout {
    id: page
    property var backend
    readonly property var about: ({
        "vllm": "OpenAI / Anthropic API；量化与推测解码支持取决于镜像和平台。",
        "sglang": "结构化生成与前缀缓存；镜像的平台支持需单独核对。",
        "llamacpp": "GGUF 模型；本机构建的 GPU 架构需与设备匹配。",
        "ollama": "通过 Ollama 模型库运行 GGUF，使用系统服务。",
        "comfyui": "视频与图像生成（MiniMax-H3）。"
    })
    readonly property var names: ({ "vllm": "vLLM", "sglang": "SGLang", "llamacpp": "llama.cpp", "ollama": "Ollama", "comfyui": "ComfyUI" })
    spacing: 16

    PageHeader { title: "引擎"; subtitle: "引擎与镜像配置。镜像配置状态不代表当前设备已通过运行验证。" }

    Repeater {
        model: page.backend.engines
        delegate: Card {
            id: e
            required property var modelData
            Layout.fillWidth: true
            padding: 18
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 4
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; text: page.names[e.modelData.engine] || e.modelData.engine; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeCard; font.weight: Font.Bold }
                    Text { textFormat: Text.PlainText; text: page.about[e.modelData.engine] || ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { textFormat: Text.PlainText;
                        visible: !!e.modelData.image
                        text: (e.modelData.tag ? e.modelData.tag + " · " : "") + String(e.modelData.image || "").replace(/@sha256:([0-9a-f]{12}).*/, "@sha256:$1…")
                        color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeCaption
                    }
                    Text { textFormat: Text.PlainText; visible: !!e.modelData.checked; text: e.modelData.checked || ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                Item { Layout.fillWidth: true }
                Pill { text: e.modelData.configured ? "镜像已配置（运行待验）" : "镜像未配置"; kind: e.modelData.configured ? "ready" : "neutral" }
            }
        }
    }
    Item { Layout.fillHeight: true }
}
