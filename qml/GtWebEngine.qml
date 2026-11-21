import QtQuick
import QtWebEngine

// Chromium-движок GT Browser. Main.qml грузит файл через Loader:
// без пакета qt6-qtwebengine Loader падает в Error и браузер остаётся на rich-text.
Item {
    id: host

    property var shell: null
    property var views: ({})
    property string currentUid: ""
    readonly property var currentView: views[currentUid] || null
    readonly property bool canGoBack: currentView ? currentView.canGoBack : false
    readonly property bool canGoForward: currentView ? currentView.canGoForward : false
    property int downloadSeq: 0
    readonly property real zoom: shell && shell.browserZoom ? shell.browserZoom : 1.0

    function downloadsDir() {
        if (shell && typeof shell.browserDownloadsDir === "function")
            return shell.browserDownloadsDir()
        var u = shell && shell.currentUser ? shell.currentUser : "misha"
        return "/home/" + u + "/Загрузки"
    }

    function ensureDownloadsDir() {
        var dir = downloadsDir()
        if (shell && typeof shell.ensureBrowserDownloadsDir === "function")
            shell.ensureBrowserDownloadsDir()
        return dir
    }

    function q(path) {
        if (shell && typeof shell.shQuote === "function")
            return shell.shQuote(path)
        return "'" + String(path || "").replace(/'/g, "'\\''") + "'"
    }

    function uniqueName(dir, name) {
        name = String(name || "download.bin").replace(/[\/\\<>:"|?*]/g, "_")
        if (!name.length)
            name = "download.bin"
        if (!shell || !shell.sys)
            return name
        var base = name
        var stem = name
        var ext = ""
        var dot = name.lastIndexOf(".")
        if (dot > 0) {
            stem = name.slice(0, dot)
            ext = name.slice(dot)
        }
        var n = 1
        while (shell.sys.run("test -e " + q(dir + "/" + base) + " && echo yes").trim() === "yes") {
            base = stem + " (" + n + ")" + ext
            n++
            if (n > 200)
                break
        }
        return base
    }

    function trackDownload(download) {
        var dir = ensureDownloadsDir()
        profile.downloadPath = dir
        download.downloadDirectory = dir
        var suggested = download.downloadFileName || "download.bin"
        var name = uniqueName(dir, suggested)
        download.downloadFileName = name
        downloadSeq++
        var id = "dl-" + downloadSeq
        download.objectName = id
        var path = dir + "/" + name
        if (shell && typeof shell.browserDownloadStarted === "function") {
            shell.browserDownloadStarted({
                id: id,
                name: name,
                path: path,
                url: download.url ? download.url.toString() : "",
                total: Number(download.totalBytes) || 0,
                received: Number(download.receivedBytes) || 0
            })
        }
        download.receivedBytesChanged.connect(function () {
            if (shell && typeof shell.browserDownloadProgress === "function") {
                shell.browserDownloadProgress({
                    id: id,
                    name: name,
                    path: path,
                    received: Number(download.receivedBytes) || 0,
                    total: Number(download.totalBytes) || 0
                })
            }
        })
        download.totalBytesChanged.connect(function () {
            if (shell && typeof shell.browserDownloadProgress === "function") {
                shell.browserDownloadProgress({
                    id: id,
                    name: name,
                    path: path,
                    received: Number(download.receivedBytes) || 0,
                    total: Number(download.totalBytes) || 0
                })
            }
        })
        download.accept()
        if (shell)
            shell.notify("Загрузка", "Сохраняю «" + name + "» в «Загрузки»", "ok")
    }

    WebEngineProfile {
        id: profile
        storageName: "gtos"
        offTheRecord: false
        persistentStoragePath: "/var/lib/gtos/browser/storage"
        cachePath: "/var/lib/gtos/browser/cache"
        httpCacheType: WebEngineProfile.DiskHttpCache
        persistentCookiesPolicy: WebEngineProfile.AllowPersistentCookies
        httpAcceptLanguage: "ru-RU,ru;q=0.9,en;q=0.8"
        downloadPath: host.downloadsDir()

        onDownloadRequested: function(download) {
            host.trackDownload(download)
        }
        onDownloadFinished: function(download) {
            if (!host.shell)
                return
            var id = download.objectName || ""
            var name = download.downloadFileName || "файл"
            var dir = download.downloadDirectory || host.downloadsDir()
            var path = dir + "/" + name
            var ok = download.state === WebEngineDownloadRequest.DownloadCompleted
            if (typeof host.shell.browserDownloadFinished === "function") {
                host.shell.browserDownloadFinished({
                    id: id,
                    name: name,
                    path: path,
                    url: download.url ? download.url.toString() : "",
                    ok: ok,
                    state: download.state
                })
            }
            if (ok)
                host.shell.notify("Загрузка завершена", "«" + name + "» — в папке «Загрузки»", "ok")
            else if (download.state === WebEngineDownloadRequest.DownloadInterrupted)
                host.shell.notify("Загрузка прервана", name, "info")
            else if (download.state === WebEngineDownloadRequest.DownloadCancelled)
                host.shell.notify("Загрузка отменена", name, "info")
        }
    }

    Timer {
        interval: 800
        running: true
        repeat: true
        onTriggered: {
            if (host.shell && typeof host.shell.refreshBrowserDownloadProgress === "function")
                host.shell.refreshBrowserDownloadProgress()
        }
    }

    Component {
        id: viewComponent
        WebEngineView {
            id: view
            property string uid: ""
            anchors.fill: parent
            visible: uid === host.currentUid
            profile: profile
            settings.javascriptCanOpenWindows: true
            settings.fullScreenSupportEnabled: true
            settings.pluginsEnabled: true
            settings.localStorageEnabled: true
            settings.focusOnNavigationEnabled: true
            settings.playbackRequiresUserGesture: true

            onUrlChanged: host.report(view)
            onTitleChanged: host.report(view)
            zoomFactor: host.zoom
            onLoadingChanged: function(info) {
                if (view.zoomFactor !== host.zoom)
                    view.zoomFactor = host.zoom
                host.report(view)
                if (info.status === WebEngineView.LoadFailedStatus && info.errorCode !== -3 && host.shell)
                    host.shell.notify("Браузер", "Не открылось: " + info.errorString, "info")
            }
            onLoadProgressChanged: host.report(view)
            onIconChanged: host.report(view)
            onNewWindowRequested: function(request) {
                if (host.shell)
                    host.shell.browserNewTab(request.requestedUrl.toString())
            }
            onFullScreenRequested: function(request) { request.accept() }
            onCertificateError: function(error) { error.rejectCertificate() }
            onNavigationRequested: function(request) {
                var u = request.url ? request.url.toString() : ""
                if (u.length && host.shell && typeof host.shell.isBrowserDownloadUrl === "function"
                        && host.shell.isBrowserDownloadUrl(u)
                        && request.navigationType !== WebEngineNavigationRequest.ReloadNavigation
                        && request.navigationType !== WebEngineNavigationRequest.BackForwardNavigation) {
                    request.reject()
                    if (typeof host.shell.browserStartUrlDownload === "function")
                        host.shell.browserStartUrlDownload(u)
                    return
                }
                request.accept()
            }
        }
    }

    function report(view) {
        if (!shell || !view)
            return
        shell.browserEngineReport(view.uid, view.url.toString(), view.title, view.loading,
                                  view.loadProgress / 100.0, view.icon.toString())
    }

    function ensureView(uid, url) {
        if (!uid.length)
            return null
        var v = views[uid]
        if (v)
            return v
        v = viewComponent.createObject(host, { uid: uid })
        if (!v)
            return null
        var map = {}
        for (var k in views)
            map[k] = views[k]
        map[uid] = v
        views = map
        if (url && url.length)
            v.url = url
        return v
    }

    function show(uid, url) {
        ensureView(uid, url)
        currentUid = uid
        if (currentView) {
            currentView.forceActiveFocus()
            report(currentView)
        }
    }

    function load(uid, url) {
        var v = ensureView(uid, "")
        if (!v)
            return
        // прямая ссылка на установщик — сразу в «Загрузки»
        if (shell && typeof shell.isBrowserDownloadUrl === "function" && shell.isBrowserDownloadUrl(url)) {
            if (typeof shell.browserStartUrlDownload === "function")
                shell.browserStartUrlDownload(url)
            return
        }
        v.url = url
        if (uid === currentUid)
            v.forceActiveFocus()
    }

    function closeView(uid) {
        var v = views[uid]
        if (!v)
            return
        var map = {}
        for (var k in views)
            if (k !== uid)
                map[k] = views[k]
        views = map
        v.destroy()
    }

    function goBack() { if (currentView) currentView.goBack() }
    function goForward() { if (currentView) currentView.goForward() }
    function reload() { if (currentView) currentView.reload() }
    function stop() { if (currentView) currentView.stop() }
    function zoomBy(delta) {
        if (shell && typeof shell.browserSetZoom === "function")
            shell.browserSetZoom(zoom + delta)
    }
    function zoomReset() {
        if (shell && typeof shell.browserSetZoom === "function")
            shell.browserSetZoom(1.0)
    }
}
