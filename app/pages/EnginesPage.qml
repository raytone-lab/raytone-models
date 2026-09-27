import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

ColumnLayout {
    id: page
    property var backend
    readonly property var about: ({
        "vllm": "OpenAI and Anthropic APIs, NVFP4 and FP8, speculative decoding. The main engine on the Thor.",
        "sglang": "Structured generation and fast prefix caching; NVIDIA's Thor build.",
        "llamacpp": "GGUF models, built for sm_110.",
        "ollama": "GGUF models with Ollama's own library; runs as a system service.",
        "comfyui": "Video and image generation (MiniMax-H3)."
    })
    readonly property var names: ({ "vllm": "vLLM", "sglang": "SGLang", "llamacpp": "llama.cpp", "ollama": "Ollama", "comfyui": "ComfyUI" })
    spacing: 16

    PageHeader { title: "Engines"; subtitle: "What runs the models. Images are pinned by digest; nothing is pulled when an engine starts." }

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
                    Text { text: page.names[e.modelData.engine] || e.modelData.engine; color: Theme.text; font.family: Theme.font; font.pixelSize: Theme.sizeCard; font.weight: Font.Bold }
                    Text { text: page.about[e.modelData.engine] || ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeBody; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text {
                        visible: !!e.modelData.image
                        text: (e.modelData.tag ? e.modelData.tag + " · " : "") + String(e.modelData.image || "").replace(/@sha256:([0-9a-f]{12}).*/, "@sha256:$1…")
                        color: Theme.muted; font.family: Theme.mono; font.pixelSize: Theme.sizeCaption
                    }
                    Text { visible: !!e.modelData.checked; text: e.modelData.checked || ""; color: Theme.muted; font.family: Theme.font; font.pixelSize: Theme.sizeCaption; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
                Item { Layout.fillWidth: true }
                Pill { text: e.modelData.configured ? "Configured" : "Not configured"; kind: e.modelData.configured ? "ready" : "neutral" }
            }
        }
    }
    Item { Layout.fillHeight: true }
}
