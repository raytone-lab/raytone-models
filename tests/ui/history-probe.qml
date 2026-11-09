import QtQuick
import Quickshell
import "app/pages"

ShellRoot {
    FloatingWindow {
        implicitWidth: 1000
        implicitHeight: 720
        visible: true

        QtObject {
            id: fixture
            property var instances: [instance("a")]
            property var stats: { return snapshot(100, 1000) }
            property var previousStats: null
            property string busy: ""

            function instance(id) {
                return { id: id, served_name: "Fixture", ready: true, current: true, engine: "vllm", port: 9000 }
            }

            function snapshot(time, counter) {
                return { time: time, memory: { total: 1024, available: 512 },
                         instances: [{ id: "a", counters: counter === null ? null : { generation_tokens: counter } }] }
            }

            function sample(counter) {
                previousStats = stats
                stats = snapshot(stats.time + 2, counter)
            }
        }

        RunningPage { id: page; backend: fixture; width: 300; height: parent.height }

        Timer {
            interval: 250
            repeat: true
            running: true
            property int phase: 0
            property int failures: 0

            function findGraph(item) {
                if (item.objectName === "running-speed-history") return item
                for (const child of item.children) {
                    const found = findGraph(child)
                    if (found) return found
                }
                return null
            }

            function check(value, name) {
                if (value) return
                failures++
                console.log("HISTORY_PROBE_FAIL", name)
            }

            function alphaAt(graph, offset, y) {
                const x = Math.floor(graph.width - offset * graph.pitch - (graph.pitch - graph.gap) / 2)
                return graph.getContext("2d").getImageData(x, y, 1, 1).data[3]
            }

            onTriggered: {
                const graph = findGraph(page)
                if (!graph) {
                    check(false, "graph missing")
                    Qt.quit()
                    return
                }
                if (phase === 0) {
                    let counter = 1000
                    for (let rate = 1; rate <= 30; rate++) {
                        counter += rate * 2
                        fixture.sample(counter)
                    }
                    fixture.sample(counter)
                    fixture.sample(null)
                } else if (phase === 1) {
                    check(graph.width > 0 && graph.width <= page.width - 40 && graph.capacity === 30,
                          "30 samples fit inside the 300px running page")
                    check(graph.samples.length === 30 && graph.samples[0] === 3 && graph.samples[27] === 30,
                          "latest 30 samples are retained")
                    check(graph.samples[28] === 0 && graph.samples[29] === null, "zero and unknown stay distinct")
                    check(alphaAt(graph, 2, 1) > 0 && alphaAt(graph, 1, 46) > 0 && alphaAt(graph, 0, 46) === 0,
                          "peak, zero mark and missing sample paint distinctly")
                    page.width = 1000
                } else if (phase === 2) {
                    check(graph.width > 300 && graph.width <= (page.width - 16) / 2 - 40 && graph.capacity === 30,
                          "chart stays inside its card after resizing to two columns")
                    check(alphaAt(graph, 2, 1) > 0 && alphaAt(graph, 0, 46) === 0, "history redraws after resize")
                    fixture.instances = [fixture.instance("b")]
                } else {
                    check(graph.samples.length === 0, "another model starts its own history")
                    if (failures === 0) console.log("HISTORY_PROBE_PASS")
                    Qt.quit()
                }
                phase++
            }
        }
    }
}
