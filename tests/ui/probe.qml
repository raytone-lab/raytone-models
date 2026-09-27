import QtQuick
import Quickshell
import "app" as App

// The app's Backend against a fake CLI (tests/ui/probe): a slow Hub answer that arrives after a
// newer request must not replace the newer one, nor hold it up. Prints PROBE lines and quits.
ShellRoot {
    App.Backend { id: backend; cli: Quickshell.env("RAYTONE_UI_FAKE_CLI") }
    Timer { interval: 100; running: true; onTriggered: { backend.openRepo("slow/repo"); backend.search("slow", "") } }
    Timer { interval: 400; running: true; onTriggered: { backend.openRepo("fast/repo"); backend.search("fast", "") } }
    function report(when) {
        console.log("PROBE " + when + " repo=" + (backend.repoDetail ? backend.repoDetail.repo : "none")
                    + " search=" + backend.searchResults.map(function (r) { return r.id }).join(",")
                    + " loadingRepo=" + backend.loadingRepo + " searching=" + backend.searching)
    }
    // the newer answer shows at once, and the slow older one (2 s) does not replace it later
    Timer { interval: 1200; running: true; onTriggered: report("early") }
    Timer { interval: 3500; running: true; onTriggered: { report("late"); Qt.quit() } }
}
