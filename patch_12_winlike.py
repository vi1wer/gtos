#!/usr/bin/env python3
"""Bump GT/OS to 1.2 and inject 12 Windows-like convenience features into Main.qml."""
from __future__ import annotations

from pathlib import Path

QML = Path(__file__).resolve().parent / "qml" / "Main.qml"


def main() -> None:
    t = QML.read_text(encoding="utf-8")
    t = t.replace('property string osVersion: "1.1"', 'property string osVersion: "1.2"', 1)

    props = """
    // GT/OS 1.2 convenience
    property bool altTabOpen: false
    property int altTabIndex: 0
    property bool calendarOpen: false
    property bool clipHistOpen: false
    property var clipHistory: []
    property bool muted: false
    property real volumeBeforeMute: 0.7
    property bool nightLight: false
    property bool showDesktopActive: false
    property var pinnedApps: ["files", "browser", "notes", "term", "settings"]
    property string filesAddress: ""
"""
    if "property bool altTabOpen" not in t:
        t = t.replace(
            'property real browserProgress: 0\n',
            'property real browserProgress: 0\n' + props,
            1,
        )

    funcs = r'''
    function appTitleOf(appId) {
        var map = {
            files: "Файлы", browser: "Браузер", mail: "Почта", notes: "Блокнот",
            term: "Терминал", settings: "Параметры", store: "Магазин", monitor: "Монитор",
            calc: "Калькулятор", cal: "Календарь", draw: "Графика", music: "Музыка",
            video: "Видео", install: "Установка GT/OS"
        }
        return map[appId] || appId
    }

    function focusOrToggleApp(appId) {
        for (var i = 0; i < windows.count; ++i) {
            if (windows.get(i).appId !== appId)
                continue
            if (!windows.get(i).hidden && windows.get(i).z === zseq) {
                windows.setProperty(i, "hidden", true)
                return
            }
            windows.setProperty(i, "hidden", false)
            windows.setProperty(i, "z", ++zseq)
            showDesktopActive = false
            return
        }
        launch(appId, appTitleOf(appId))
    }

    function runningAppIds() {
        var out = []
        for (var i = 0; i < windows.count; ++i) {
            var id = windows.get(i).appId
            if (out.indexOf(id) < 0)
                out.push(id)
        }
        return out
    }

    function dockAppList() {
        var seen = {}
        var out = []
        var i
        for (i = 0; i < pinnedApps.length; ++i) {
            out.push(pinnedApps[i])
            seen[pinnedApps[i]] = true
        }
        var run = runningAppIds()
        for (i = 0; i < run.length; ++i) {
            if (!seen[run[i]])
                out.push(run[i])
        }
        return out
    }

    function isAppRunning(appId) {
        for (var i = 0; i < windows.count; ++i)
            if (windows.get(i).appId === appId && !windows.get(i).hidden)
                return true
        for (var j = 0; j < windows.count; ++j)
            if (windows.get(j).appId === appId)
                return true
        return false
    }

    function isAppActive(appId) {
        var topZ = -1
        var topId = ""
        for (var i = 0; i < windows.count; ++i) {
            var w = windows.get(i)
            if (!w.hidden && w.z > topZ) {
                topZ = w.z
                topId = w.appId
            }
        }
        return topId === appId
    }

    function togglePinApp(appId) {
        var arr = pinnedApps.slice()
        var ix = arr.indexOf(appId)
        if (ix >= 0)
            arr.splice(ix, 1)
        else
            arr.push(appId)
        pinnedApps = arr
        saveDesktop()
        notify("Панель задач", ix >= 0 ? "Откреплено" : "Закреплено: " + appTitleOf(appId), "ok")
    }

    function toggleShowDesktop() {
        if (!showDesktopActive) {
            for (var i = 0; i < windows.count; ++i)
                windows.setProperty(i, "hidden", true)
            showDesktopActive = true
            closeCtxMenu()
            startOpen = false
            quickOpen = false
        } else {
            for (var j = 0; j < windows.count; ++j)
                windows.setProperty(j, "hidden", false)
            showDesktopActive = false
        }
    }

    function toggleMute() {
        if (!muted) {
            volumeBeforeMute = volume
            volume = 0
            muted = true
        } else {
            volume = volumeBeforeMute > 0 ? volumeBeforeMute : 0.5
            muted = false
        }
        saveDesktop()
    }

    function pushClipboard(text) {
        if (!text || !text.length)
            return
        var arr = [text].concat(clipHistory)
        if (arr.length > 12)
            arr = arr.slice(0, 12)
        clipHistory = arr
    }

    function openAltTab() {
        var ids = runningAppIds()
        if (!ids.length) {
            launch("files", "Файлы")
            return
        }
        altTabOpen = true
        altTabIndex = 0
        startOpen = false
        quickOpen = false
        closeCtxMenu()
    }

    function confirmAltTab() {
        var ids = runningAppIds()
        if (!ids.length) {
            altTabOpen = false
            return
        }
        var id = ids[Math.max(0, Math.min(altTabIndex, ids.length - 1))]
        altTabOpen = false
        focusOrToggleApp(id)
        for (var i = 0; i < windows.count; ++i) {
            if (windows.get(i).appId === id)
                windows.setProperty(i, "hidden", false)
        }
    }

    function takeScreenshot() {
        var name = "Снимок_" + Qt.formatDateTime(new Date(), "yyyyMMdd_HHmmss") + ".png"
        var path = "/home/" + currentUser + "/Изображения/" + name
        sys.run("mkdir -p " + shQuote("/home/" + currentUser + "/Изображения"))
        deskCapture.targetPath = path
        deskCapture.grabToImage(function (result) {
            if (result.saveToFile(path))
                notify("Снимок экрана", "Сохранено в Изображения\\n" + name, "ok")
            else {
                sys.writeFile(path.replace(".png", ".txt"), "Снимок GT/OS " + osVersion + " · " + name + "\n")
                notify("Снимок экрана", "Сохранена заметка снимка в Изображения", "ok")
            }
        })
    }

    function goFilesAddress() {
        var p = filesAddress.trim()
        if (!p.length)
            return
        if (p === "Этот компьютер" || p.toLowerCase() === "thispc")
            loadFiles("thispc")
        else
            loadFiles(p)
    }
'''
    if "function focusOrToggleApp" not in t:
        t = t.replace(
            "    function browseReload() {\n        if (browserUrl.trim().length)\n            browseGo(false)\n    }\n",
            "    function browseReload() {\n        if (browserUrl.trim().length)\n            browseGo(false)\n    }\n" + funcs,
            1,
        )

    # Extend desktop/files context menus
    t = t.replace(
        """    function desktopCtxItems() {
        return [
            { label: "Параметры", action: "settings" },
            { label: "Персонализация", action: "wallpaper" },
            { label: "Файлы", action: "files" },
            { label: "Терминал", action: "term" },
            { label: "Браузер", action: "browser" },
            { label: "Обновить", action: "refresh" },
            { label: "Заблокировать", action: "lock" }
        ]
    }""",
        """    function desktopCtxItems() {
        return [
            { label: "Параметры", action: "settings" },
            { label: "Персонализация", action: "wallpaper" },
            { label: "Файлы", action: "files" },
            { label: "Терминал", action: "term" },
            { label: "Браузер", action: "browser" },
            { label: "Снимок экрана", action: "shot" },
            { label: "Показать рабочий стол", action: "desk" },
            { label: "Обновить", action: "refresh" },
            { label: "Заблокировать", action: "lock" }
        ]
    }""",
    )
    t = t.replace(
        """    function filesCtxItems() {
        return [
            { label: "Открыть", action: "open" },
            { label: "Копировать", action: "copy" },
            { label: "Вставить", action: "paste" },
            { label: "Удалить", action: "del" },
            { label: "Новая папка", action: "newdir" }
        ]
    }""",
        """    function filesCtxItems() {
        return [
            { label: "Открыть", action: "open" },
            { label: "Копировать", action: "copy" },
            { label: "Вставить", action: "paste" },
            { label: "Удалить", action: "del" },
            { label: "Новая папка", action: "newdir" },
            { label: "Снимок экрана", action: "shot" }
        ]
    }""",
    )
    if 'else if (action === "shot")' not in t:
        t = t.replace(
            'else if (action === "wallpaper") { settingsSection = "personalize"; launch("settings", "Параметры") }\n    }',
            'else if (action === "wallpaper") { settingsSection = "personalize"; launch("settings", "Параметры") }\n'
            '        else if (action === "shot") takeScreenshot()\n'
            '        else if (action === "desk") toggleShowDesktop()\n'
            '        else if (action === "clip") { clipHistOpen = true }\n'
            '    }',
        )

    # save/load pinned + night
    if '"pins="' not in t:
        t = t.replace(
            '"avatar=" + userAvatar\n        ].join("\\n")',
            '"avatar=" + userAvatar,\n'
            '            "pins=" + pinnedApps.join(","),\n'
            '            "night=" + (nightLight ? "1" : "0")\n'
            '        ].join("\\n")',
        )
        t = t.replace(
            'else if (k === "avatar" && v.length) userAvatar = v\n        }\n    }',
            'else if (k === "avatar" && v.length) userAvatar = v\n'
            '            else if (k === "pins" && v.length) pinnedApps = v.split(",").filter(function (x) { return x.length })\n'
            '            else if (k === "night") nightLight = v === "1"\n'
            '        }\n    }',
        )

    # copy also pushes clipboard history
    if "pushClipboard(selectedName)" not in t:
        t = t.replace(
            'notify("Файлы", "Скопировано: " + selectedName, "ok")',
            'pushClipboard(selectedName)\n        notify("Файлы", "Скопировано: " + selectedName, "ok")',
            1,
        )

    # clock opens calendar
    t = t.replace(
        """                onClicked: {
                    root.notifyCenterOpen = !root.notifyCenterOpen
                    root.quickOpen = false
                    root.startOpen = false
                }""",
        """                onClicked: {
                    root.calendarOpen = !root.calendarOpen
                    if (root.calendarOpen)
                        root.notifyCenterOpen = true
                    root.quickOpen = false
                    root.startOpen = false
                    root.clipHistOpen = false
                }""",
    )

    # dock buttons — replace static dock apps with repeater + show desktop
    old_dock = """            DockButton { kind: "files"; onClicked: root.launch("files", "Файлы") }
            DockButton { kind: "browser"; visible: root.dockShowBrowser; onClicked: root.launch("browser", "Браузер") }
            DockButton { kind: "mail"; visible: root.dockShowMail; onClicked: root.launch("mail", "Почта") }
            DockButton { kind: "notes"; onClicked: root.launch("notes", "Блокнот") }
            DockButton { kind: "term"; onClicked: root.launch("term", "Терминал") }
            DockButton { kind: "settings"; onClicked: root.launch("settings", "Настройки") }
            DockButton { kind: "grid"; onClicked: {} }"""
    new_dock = """            Repeater {
                model: root.dockAppList()
                delegate: Item {
                    width: 46; height: 50
                    visible: (modelData !== "browser" || root.dockShowBrowser) && (modelData !== "mail" || root.dockShowMail)
                    DockButton {
                        kind: modelData === "settings" ? "settings" : (modelData === "files" ? "files" : (modelData === "browser" ? "browser" : (modelData === "mail" ? "mail" : (modelData === "notes" ? "notes" : (modelData === "term" ? "term" : "grid")))))
                        anchors.horizontalCenter: parent.horizontalCenter
                        onClicked: root.focusOrToggleApp(modelData)
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        width: root.isAppActive(modelData) ? 18 : 6
                        height: 3
                        radius: 1.5
                        visible: root.isAppRunning(modelData)
                        color: root.isAppActive(modelData) ? root.accentColor : "#8b98a3"
                    }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        onClicked: root.openCtxMenuAt(this, mouse.x, mouse.y, [
                            { label: "Открыть", action: "files" },
                            { label: root.pinnedApps.indexOf(modelData) >= 0 ? "Открепить" : "Закрепить", action: "pin:" + modelData }
                        ])
                    }
                }
            }
            Rectangle {
                width: 40; height: 40; radius: 10
                color: deskBtn.containsMouse ? "#243038" : "transparent"
                Text { anchors.centerIn: parent; text: "▦"; color: "#d5dde3"; font.pixelSize: 14 }
                MouseArea {
                    id: deskBtn; anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleShowDesktop()
                }
            }"""
    if "function dockAppList" in t and old_dock in t:
        t = t.replace(old_dock, new_dock)

    # pin action in runCtxAction
    if 'action.indexOf("pin:")' not in t:
        t = t.replace(
            'else if (action === "clip") { clipHistOpen = true }\n    }',
            'else if (action === "clip") { clipHistOpen = true }\n'
            '        else if (action.indexOf("pin:") === 0) togglePinApp(action.slice(4))\n'
            '        else if (action === "files" || action === "term" || action === "browser" || action === "settings") {\n'
            '            /* handled above */\n'
            '        }\n'
            '    }',
        )

    # Shortcuts + overlays + desktop icons + night light + capture item
    marker = "    // Global context menu\n    Item {\n        id: ctxLayer"
    inject = r'''
    // Invisible capture surface for screenshots
    Item {
        id: deskCapture
        anchors.fill: parent
        z: -1
        property string targetPath: ""
        visible: false
    }

    // Desktop icons (Win-like)
    Column {
        z: 6
        x: 28
        y: 70
        spacing: 18
        Repeater {
            model: [
                { label: "Этот компьютер", app: "files", path: "thispc" },
                { label: "Файлы", app: "files", path: "" },
                { label: "Корзина", app: "files", path: "trash" },
                { label: "Параметры", app: "settings", path: "" }
            ]
            delegate: Item {
                width: 84; height: 88
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 48; height: 48; radius: 12
                    color: "#1a2126cc"
                    border.color: "#2c3840"; border.width: 1
                    Text { anchors.centerIn: parent; text: index === 0 ? "▣" : (index === 2 ? "⌫" : (index === 3 ? "⚙" : "📁")); color: "#e8eef2"; font.pixelSize: 20 }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    text: modelData.label
                    color: "#f4f7f8"; font.pixelSize: 11; font.family: "DejaVu Sans"
                    style: Text.Outline; styleColor: "#00000088"
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onDoubleClicked: {
                        if (modelData.app === "settings")
                            root.launch("settings", "Параметры")
                        else if (modelData.path === "thispc") {
                            root.launch("files", "Файлы"); root.loadFiles("thispc")
                        } else if (modelData.path === "trash") {
                            root.launch("files", "Файлы"); root.loadFiles("/home/" + root.currentUser + "/.Корзина")
                        } else
                            root.launch("files", "Файлы")
                    }
                    onClicked: if (mouse.button === Qt.RightButton)
                        root.openCtxMenuAt(this, mouse.x, mouse.y, root.desktopCtxItems())
                }
            }
        }
    }

    // Night light warm filter
    Rectangle {
        anchors.fill: parent
        z: 8
        visible: root.nightLight
        color: "#44ff8c3a"
        opacity: 0.22
    }

    Shortcut { sequence: "Alt+Tab"; onActivated: root.openAltTab() }
    Shortcut { sequence: "Alt+Backtab"; onActivated: root.openAltTab() }
    Shortcut { sequence: "Meta+D"; onActivated: root.toggleShowDesktop() }
    Shortcut { sequence: "Ctrl+Meta+D"; onActivated: root.toggleShowDesktop() }
    Shortcut { sequence: "Meta+L"; onActivated: root.lockSession() }
    Shortcut { sequence: "Meta+E"; onActivated: root.launch("files", "Файлы") }
    Shortcut { sequence: "Meta+I"; onActivated: { root.settingsSection = "home"; root.launch("settings", "Параметры") } }
    Shortcut { sequence: "Meta+V"; onActivated: { root.clipHistOpen = !root.clipHistOpen; root.quickOpen = false } }
    Shortcut { sequence: "Print"; onActivated: root.takeScreenshot() }
    Shortcut { sequence: "Meta+Shift+S"; onActivated: root.takeScreenshot() }
    Shortcut { sequence: "Esc"; onActivated: {
            root.altTabOpen = false
            root.clipHistOpen = false
            root.calendarOpen = false
            root.closeCtxMenu()
            if (root.startOpen) root.startOpen = false
        } }

    // Alt+Tab switcher
    Rectangle {
        anchors.fill: parent
        z: 920
        visible: root.altTabOpen
        color: "#99000000"
        MouseArea { anchors.fill: parent; onClicked: root.altTabOpen = false }
        Row {
            anchors.centerIn: parent
            spacing: 14
            Repeater {
                model: root.runningAppIds()
                delegate: Rectangle {
                    width: 120; height: 100; radius: 12
                    color: index === root.altTabIndex ? "#2a3842" : "#1a2126"
                    border.width: index === root.altTabIndex ? 2 : 1
                    border.color: index === root.altTabIndex ? root.accentColor : "#2c3840"
                    Column {
                        anchors.centerIn: parent; spacing: 8
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "▣"; color: root.accentColor; font.pixelSize: 28 }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.appTitleOf(modelData); color: "#e8eef2"; font.pixelSize: 12 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: { root.altTabIndex = index; root.confirmAltTab() }
                    }
                }
            }
        }
        Timer {
            interval: 40; running: root.altTabOpen; repeat: true
            onTriggered: {
                // cycle while Alt held is hard in QML; click or Enter confirms
            }
        }
        Keys.onPressed: function (e) {
            if (e.key === Qt.Key_Tab) {
                var n = root.runningAppIds().length
                if (n > 0) root.altTabIndex = (root.altTabIndex + 1) % n
                e.accepted = true
            } else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter) {
                root.confirmAltTab(); e.accepted = true
            }
        }
        Component.onCompleted: forceActiveFocus()
        onVisibleChanged: if (visible) forceActiveFocus()
    }

    // Clipboard history
    Rectangle {
        z: 96
        visible: root.clipHistOpen
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 18
        anchors.bottomMargin: root.dockSize + 28
        width: 320
        height: 360
        radius: 16
        color: "#121a20"
        border.color: "#2a3842"; border.width: 1
        Column {
            anchors.fill: parent; anchors.margins: 14; spacing: 10
            Text { text: "Буфер обмена"; color: "#f4f7f8"; font.bold: true; font.pixelSize: 15 }
            Text { text: "Win+V · последние копии"; color: "#9aa7b2"; font.pixelSize: 11 }
            Flickable {
                width: parent.width; height: parent.height - 50
                contentHeight: clipCol.height; clip: true
                Column {
                    id: clipCol; width: parent.width; spacing: 6
                    Repeater {
                        model: root.clipHistory
                        delegate: Rectangle {
                            width: parent.width; height: 52; radius: 8; color: "#1c262e"
                            Text {
                                anchors.fill: parent; anchors.margins: 10
                                text: modelData; color: "#e8eef2"; font.pixelSize: 12
                                elide: Text.ElideRight; wrapMode: Text.Wrap; maximumLineCount: 2
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    root.clipPath = ""
                                    root.notify("Буфер", "Выбрано: " + modelData, "ok")
                                    root.clipHistOpen = false
                                }
                            }
                        }
                    }
                    Text {
                        visible: root.clipHistory.length === 0
                        text: "Пока пусто — скопируйте файл в проводнике"
                        color: "#6b7785"; font.pixelSize: 12; width: parent.width; wrapMode: Text.Wrap
                    }
                }
            }
        }
    }

    // Calendar flyout (alongside notify)
    Rectangle {
        z: 96
        visible: root.calendarOpen
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: 18
        anchors.topMargin: 52
        width: 280
        height: 220
        radius: 16
        color: "#121a20"
        border.color: "#2a3842"; border.width: 1
        Column {
            anchors.fill: parent; anchors.margins: 16; spacing: 10
            Text { text: Qt.formatTime(root.now, "HH:mm"); color: "#fff"; font.pixelSize: 42; font.bold: true }
            Text { text: root.dateLine(); color: "#9aa7b2"; font.pixelSize: 14 }
            Rectangle { width: parent.width; height: 1; color: "#243038" }
            Text { text: "Календарь GT/OS " + root.osVersion; color: "#d5dde3"; font.pixelSize: 13 }
            Rectangle {
                width: parent.width; height: 36; radius: 8; color: "#1c262e"
                Text { anchors.centerIn: parent; text: "Открыть календарь"; color: "#e8eef2"; font.pixelSize: 12 }
                MouseArea { anchors.fill: parent; onClicked: { root.calendarOpen = false; root.launch("cal", "Календарь") } }
            }
        }
    }

'''
    if "id: deskCapture" not in t and marker in t:
        t = t.replace(marker, inject + marker)

    # Quick settings: mute + night light + clipboard + screenshot
    if "Ночной свет" not in t:
        t = t.replace(
            """            Text {
                text: "Монитор системы →"
                color: root.accentColor
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    onClicked: { root.quickOpen = false; root.launch("monitor", "Монитор") }
                }
            }
        }
    }""",
            """            Row {
                spacing: 8
                Rectangle {
                    width: 90; height: 36; radius: 10
                    color: root.muted ? "#7f1d1d" : "#1c262e"
                    Text { anchors.centerIn: parent; text: root.muted ? "Звук выкл" : "Без звука"; color: "#e8eef2"; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: root.toggleMute() }
                }
                Rectangle {
                    width: 90; height: 36; radius: 10
                    color: root.nightLight ? "#ca5010" : "#1c262e"
                    Text { anchors.centerIn: parent; text: "Ночь"; color: "#e8eef2"; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: { root.nightLight = !root.nightLight; root.saveDesktop() } }
                }
                Rectangle {
                    width: 90; height: 36; radius: 10; color: "#1c262e"
                    Text { anchors.centerIn: parent; text: "Снимок"; color: "#e8eef2"; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: { root.quickOpen = false; root.takeScreenshot() } }
                }
            }
            Text {
                text: "Буфер обмена (Win+V) →"
                color: root.accentColor
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    onClicked: { root.quickOpen = false; root.clipHistOpen = true }
                }
            }
            Text {
                text: "Монитор системы →"
                color: root.accentColor
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    onClicked: { root.quickOpen = false; root.launch("monitor", "Монитор") }
                }
            }
        }
    }""",
        )

    # Explorer address bar editable — replace Text with TextInput in nav path label area
    old_addr = """                        Rectangle {
                            width: parent.width - 220
                            height: 32
                            radius: 4
                            color: "#0c1216"
                            border.color: "#243038"
                            border.width: 1
                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                verticalAlignment: Text.AlignVCenter
                                text: root.filesPath === "/" ? "Этот компьютер › Локальный диск (C:)"
                                      : (root.filesPath === "fav" ? "Быстрый доступ"
                                      : (root.filesPath === "thispc" ? "Этот компьютер"
                                      : root.filesPathLabel()))
                                color: "#e8eef2"
                                font.pixelSize: 12
                                font.family: "DejaVu Sans"
                                elide: Text.ElideMiddle
                            }
                        }"""
    # flexible match - find by unique snippet
    if "filesAddress" in t and "goFilesAddress" in t:
        needle = 'text: root.filesPath === "/" ? "Этот компьютер › Локальный диск (C:)"'
        if needle in t and "id: addrInput" not in t:
            # Replace the Text block that shows path with TextInput
            import re
            pattern = re.compile(
                r'(Rectangle \{\s*width: parent\.width - 220\s*height: 32\s*radius: 4\s*color: "#0c1216"\s*border\.color: "#243038"\s*border\.width: 1\s*)Text \{.*?elide: Text\.ElideMiddle\s*\}\s*\}',
                re.S,
            )
            repl = r'''\1TextInput {
                                id: addrInput
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                verticalAlignment: Text.AlignVCenter
                                color: "#e8eef2"
                                font.pixelSize: 12
                                font.family: "DejaVu Sans"
                                selectByMouse: true
                                text: root.filesPath === "/" ? "/"
                                      : (root.filesPath === "fav" ? "Быстрый доступ"
                                      : (root.filesPath === "thispc" ? "Этот компьютер"
                                      : root.filesPath))
                                onActiveFocusChanged: if (activeFocus) root.filesAddress = text
                                onTextChanged: root.filesAddress = text
                                Keys.onReturnPressed: root.goFilesAddress()
                                Keys.onEnterPressed: root.goFilesAddress()
                            }
                        }'''
            t2, n = pattern.subn(repl, t, count=1)
            if n:
                t = t2
            else:
                print("warn: address bar pattern not replaced")

    QML.write_text(t, encoding="utf-8")
    print(f"patched {QML} -> 1.2 features")


if __name__ == "__main__":
    main()
