// Adapted from OmaStats HistoryGraph.qml at commit 495eabdcbd232ba2d6fb4eefcd996248176cca52.
// https://github.com/crmne/omastats/blob/495eabdcbd232ba2d6fb4eefcd996248176cca52/ui/HistoryGraph.qml
//
// MIT License
//
// Copyright (c) 2026 Carmine Paolino
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

import QtQuick
import ".."

Canvas {
    id: root

    property var samples: []
    readonly property int sampleLimit: 30
    readonly property color barColor: Theme.accent
    readonly property color baselineColor: Theme.border
    readonly property int pitch: Math.max(1, Math.min(15, Math.floor(width / sampleLimit)))
    readonly property int gap: Math.min(pitch - 1, Math.round(pitch * 0.4))
    readonly property int capacity: Math.min(sampleLimit, Math.floor(width / pitch))
    readonly property real devicePixelRatio: Screen.devicePixelRatio || 1

    antialiasing: false

    onSamplesChanged: requestPaint()
    onBarColorChanged: requestPaint()
    onBaselineColorChanged: requestPaint()
    onDevicePixelRatioChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onAvailableChanged: if (available) requestPaint()
    onVisibleChanged: if (visible) requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        if (width <= 0 || height <= 1) return

        const dpr = root.devicePixelRatio
        const pixel = 1 / dpr
        const snap = value => Math.round(value * dpr) / dpr
        const bottom = snap(height - 1)
        const start = Math.max(0, samples.length - capacity)
        const recent = samples.slice(start)
        const peak = recent.reduce((max, value) => Number.isFinite(value) ? Math.max(max, value) : max, 1)

        ctx.fillStyle = root.barColor
        for (let i = 0; i < recent.length; i++) {
            const value = recent[i]
            if (!Number.isFinite(value) || value < 0) continue
            const slot = width - (recent.length - i) * pitch
            const left = Math.max(0, snap(slot + gap))
            const right = Math.min(width, snap(slot + pitch))
            const top = Math.max(0, Math.min(bottom - pixel, snap(bottom * (1 - value / peak))))
            ctx.fillRect(left, top, right - left, bottom - top)
        }

        ctx.fillStyle = root.baselineColor
        ctx.fillRect(0, bottom, width, height - bottom)
    }
}
