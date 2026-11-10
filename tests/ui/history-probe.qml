import QtQuick
import Quickshell
import "app/components"
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
            property var pageState: null
            property var connection: null

            function instance(id) {
                return { id: id, served_name: "Fixture", ready: true, current: true, engine: "vllm", port: 9000 }
            }

            function snapshot(time, counter) {
                return { time: time, memory: { total: 34359738368, available: 17179869184 },
                         instances: [{ id: "a", counters: counter === null ? null : { generation_tokens: counter } }] }
            }

            function sample(counter) {
                previousStats = stats
                stats = snapshot(stats.time + 2, counter)
            }
        }

        RunningPage { id: page; backend: fixture; width: 300; height: parent.height }
        ProgressLine { id: probeMeter; width: 100; visible: false }

        Timer {
            interval: 250
            repeat: true
            running: true
            property int phase: 0
            property int failures: 0

            function findItem(item, name) {
                if (item.objectName === name) return item
                for (const child of item.children) {
                    const found = findItem(child, name)
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

            function fitsCard(item, card) {
                const left = item.mapToItem(card, 0, 0).x
                return item.width > 0 && left >= card.padding - 0.5
                    && left + item.width <= card.width - card.padding + 0.5
            }

            onTriggered: {
                const graph = findItem(page, "running-speed-history")
                const meter = findItem(page, "running-memory-meter")
                const fill = findItem(probeMeter, "meter-fill")
                if (!graph || !meter || !fill) {
                    check(false, "telemetry controls missing")
                    Qt.quit()
                    return
                }
                const graphCard = graph.parent.parent
                const meterCard = meter.parent.parent
                if (phase === 0) {
                    check(probeMeter.height === 6 && meter.height === 6, "shared six-pixel meter height")
                    const ratios = [[0, 0], [0.01, 1], [0.5, 50], [1, 100], [1.1, 100], [-0.1, 0], [NaN, 0], [null, 0]]
                    for (const [ratio, pixels] of ratios) {
                        probeMeter.value = ratio
                        check(Math.abs(fill.width - pixels) < 0.001, "exact fill width for " + ratio)
                    }
                    check(meter.ratio === 0.5, "known memory usage")
                    let counter = 1000
                    for (let rate = 1; rate <= 30; rate++) {
                        counter += rate * 2
                        fixture.sample(counter)
                    }
                    fixture.sample(counter)
                    fixture.sample(null)
                } else if (phase === 1) {
                    check(fitsCard(graph, graphCard) && fitsCard(meter, meterCard) && graph.capacity === 30
                          && graphCard.x === meterCard.x && graphCard.y < meterCard.y,
                          "telemetry fits inside the stacked cards at 300px")
                    check(graph.samples.length === 30 && graph.samples[0] === 3 && graph.samples[27] === 30,
                          "latest 30 samples are retained")
                    check(graph.samples[28] === 0 && graph.samples[29] === null, "zero and unknown stay distinct")
                    check(alphaAt(graph, 2, 1) > 0 && alphaAt(graph, 1, 46) > 0 && alphaAt(graph, 0, 46) === 0,
                          "peak, zero mark and missing sample paint distinctly")
                    page.width = 1000
                } else if (phase === 2) {
                    check(fitsCard(graph, graphCard) && fitsCard(meter, meterCard) && graph.capacity === 30
                          && graphCard.x < meterCard.x && graphCard.y === meterCard.y && graphCard.height === meterCard.height,
                          "telemetry fits inside aligned cards at 1000px")
                    check(alphaAt(graph, 2, 1) > 0 && alphaAt(graph, 0, 46) === 0, "history redraws after resize")
                    fixture.stats = { time: fixture.stats.time, memory: { total: 0, available: 0 } }
                    fixture.instances = [fixture.instance("b")]
                } else {
                    check(graph.samples.length === 0, "another model starts its own history")
                    check(meter.ratio === null, "unknown memory is distinct from zero usage")
                    if (failures === 0) console.log("HISTORY_PROBE_PASS")
                    Qt.quit()
                }
                phase++
            }
        }
    }
}
