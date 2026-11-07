#!/usr/bin/env python3
"""Theme file explorer to GT Dark; rebuild Start + notifications."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "qml" / "Main.qml"


def theme_files(t: str) -> str:
    a = t.find("        id: filesPage")
    b = t.find("        id: settingsPage")
    if a < 0 or b < 0:
        raise SystemExit("filesPage markers missing")
    chunk = t[a:b]
    for old, new in [
        ("#f3f3f3", "#0c1216"),
        ("#f9f9f9", "#0f1519"),
        ("#ffffff", "#121a20"),
        ("#fafafa", "#0e1519"),
        ("#1a1a1a", "#e8eef2"),
        ("#605e5c", "#9aa7b2"),
        ("#0078d4", "#3be182"),
        ("#cce8ff", "#16352e"),
        ("#e8e8e8", "#1c262e"),
        ("#ebebeb", "#182228"),
        ("#e5e5e5", "#243038"),
        ("#8a8886", "#2a3842"),
        ("#a19f9d", "#5f6c76"),
        ("#e8f4fc", "#152828"),
        ("#d0d0d0", "#2a3842"),
        ("#a4262c", "#7f1d1d"),
        ('color: "white"', 'color: "#06210f"'),
    ]:
        chunk = chunk.replace(old, new)
    chunk = chunk.replace(
        'Text { anchors.centerIn: parent; text: "Назад"; color: "#e8eef2"',
        'Text { anchors.centerIn: parent; text: "Назад"; color: "#06210f"',
    )
    chunk = chunk.replace(
        'Text { anchors.centerIn: parent; text: "C:"; color: "#e8eef2"; font.bold: true }',
        'Text { anchors.centerIn: parent; text: "C:"; color: "#06210f"; font.bold: true }',
    )
    # toolbar tab labels
    chunk = chunk.replace(
        'Text { text: "Файл"; color: "#3be182"; font.pixelSize: 13; font.bold: true; font.family: "DejaVu Sans" }',
        'Text { text: "Проводник GT"; color: "#6ee7b7"; font.pixelSize: 13; font.bold: true; font.family: "DejaVu Sans" }',
    )
    return t[:a] + chunk + t[b:]


LAUNCHER = r'''
    Rectangle {
        id: launcher
        z: 30
        width: 720
        height: 640
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.dockSize + 36
        radius: 28
        color: "#12181e"
        border.width: 1
        border.color: "#2a3842"
        opacity: root.startOpen ? 1 : 0
        scale: root.startOpen ? 1 : 0.96
        visible: root.startOpen || opacity > 0
        transformOrigin: Item.Bottom
        clip: true
        onVisibleChanged: if (visible) root.loadRecent()
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

        // soft top glow
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 3
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#3be182" }
                GradientStop { position: 1.0; color: "#1aa66a" }
            }
            opacity: 0.85
        }

        Column {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 16

            // user + search
            Row {
                width: parent.width
                spacing: 14
                Rectangle {
                    width: 48; height: 48; radius: 24
                    color: "#16352e"
                    border.width: 1; border.color: "#3be182"
                    Text {
                        anchors.centerIn: parent
                        text: root.currentUser.length ? root.currentUser.charAt(0).toUpperCase() : "G"
                        color: "#6ee7b7"; font.pixelSize: 18; font.bold: true; font.family: "DejaVu Sans"
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    width: parent.width - 62
                    Text {
                        text: "Привет, " + (root.currentUser.length ? root.currentUser : "гость")
                        color: "#f4f7f8"; font.pixelSize: 16; font.bold: true; font.family: "DejaVu Sans"
                    }
                    Text {
                        text: "GT/OS " + root.osVersion + " · меню Пуск"
                        color: "#7e8b96"; font.pixelSize: 12; font.family: "DejaVu Sans"
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 46
                radius: 14
                color: "#0c1216"
                border.width: 1
                border.color: search.activeFocus ? root.accentColor : "#243038"
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: "⌕"; color: "#6ee7b7"; font.pixelSize: 16
                }
                TextInput {
                    id: search
                    anchors.fill: parent
                    anchors.leftMargin: 40
                    anchors.rightMargin: 14
                    verticalAlignment: Text.AlignVCenter
                    color: "#f4f7f8"
                    font.pixelSize: 15
                    font.family: "DejaVu Sans"
                    clip: true
                    selectByMouse: true
                    text: root.query
                    onTextChanged: root.query = text
                }
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 40
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Поиск приложений и файлов"
                    color: "#5f6c76"; font.pixelSize: 14; font.family: "DejaVu Sans"
                    visible: search.text.length === 0 && !search.activeFocus
                }
            }

            // pinned
            Text {
                text: "Закреплённые"
                color: "#9aa7b2"; font.pixelSize: 12; font.bold: true
                font.letterSpacing: 0.6
            }

            Flickable {
                width: parent.width
                height: 280
                clip: true
                contentHeight: appGrid.height
                Grid {
                    id: appGrid
                    width: parent.width
                    columns: 5
                    rowSpacing: 10
                    columnSpacing: 4
                    AppTile { label: "Файлы"; tileColor: "#3d6b4a"; tileRadius: 16; kind: "files"; visible: root.matches(label); onClicked: root.launch("files", "Файлы") }
                    AppTile { label: "Браузер"; tileColor: "#2f6fed"; tileRadius: 18; kind: "browser"; visible: root.matches(label); onClicked: root.launch("browser", "Браузер") }
                    AppTile { label: "Почта"; tileColor: "#5b8fa8"; tileRadius: 16; kind: "mail"; visible: root.matches(label); onClicked: root.launch("mail", "Почта") }
                    AppTile { label: "Блокнот"; tileColor: "#c9a227"; tileRadius: 16; kind: "notes"; visible: root.matches(label); onClicked: root.launch("notes", "Блокнот") }
                    AppTile { label: "Терминал"; tileColor: "#1f6a3c"; tileRadius: 16; kind: "term"; visible: root.matches(label); onClicked: root.launch("term", "Терминал") }
                    AppTile { label: "Калькулятор"; tileColor: "#3b78e6"; tileRadius: 16; kind: "grid"; visible: root.matches(label); onClicked: root.launch("calc", "Калькулятор") }
                    AppTile { label: "Календарь"; tileColor: "#4a7c59"; tileRadius: 16; kind: "cal"; visible: root.matches(label); onClicked: root.launch("cal", "Календарь") }
                    AppTile { label: "Графика"; tileColor: "#5c54c4"; tileRadius: 16; kind: "draw"; visible: root.matches(label); onClicked: root.launch("draw", "Графика") }
                    AppTile { label: "Музыка"; tileColor: "#b83280"; tileRadius: 16; kind: "music"; visible: root.matches(label); onClicked: root.launch("music", "Музыка") }
                    AppTile { label: "Монитор"; tileColor: "#0ea5e9"; tileRadius: 16; kind: "grid"; visible: root.matches(label); onClicked: root.launch("monitor", "Монитор") }
                    AppTile { label: "Магазин"; tileColor: "#2563eb"; tileRadius: 16; kind: "store"; visible: root.matches(label); onClicked: root.launch("store", "Магазин") }
                    AppTile { label: "Настройки"; tileColor: "#4a5560"; tileRadius: 16; kind: "settings"; visible: root.matches(label); onClicked: root.launch("settings", "Настройки") }
                    AppTile { label: "Видео"; tileColor: "#6a3ad8"; tileRadius: 16; kind: "video"; visible: root.matches(label); onClicked: root.launch("video", "Видео") }
                    AppTile { label: "Установка"; tileColor: "#0f766e"; tileRadius: 16; kind: "grid"; visible: root.matches(label); onClicked: root.launch("install", "Установка GT/OS") }
                }
            }

            Text {
                text: "Недавние"
                color: "#9aa7b2"; font.pixelSize: 12; font.bold: true
                visible: root.query.length === 0
            }

            Column {
                width: parent.width
                spacing: 4
                visible: root.query.length === 0
                height: Math.min(120, root.recent.length * 40)
                Repeater {
                    model: root.recent
                    delegate: Rectangle {
                        width: parent.width
                        height: 36
                        radius: 10
                        color: rh.containsMouse ? "#1c262e" : "transparent"
                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            spacing: 10
                            Rectangle {
                                width: 24; height: 24; radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: "#16352e"
                                Text { anchors.centerIn: parent; text: "≡"; color: "#6ee7b7"; font.pixelSize: 11 }
                            }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 50
                                Text { text: modelData.name; color: "#e8eef2"; font.pixelSize: 13; elide: Text.ElideRight; width: parent.width }
                                Text { text: modelData.meta; color: "#7e8b96"; font.pixelSize: 10; elide: Text.ElideRight; width: parent.width }
                            }
                        }
                        MouseArea {
                            id: rh; anchors.fill: parent; hoverEnabled: true
                            onClicked: root.openRecent(modelData.path)
                        }
                    }
                }
                Text {
                    visible: root.recent.length === 0
                    text: "Пока нет недавних файлов"
                    color: "#5f6c76"; font.pixelSize: 12
                }
            }

            Item { width: 1; height: 4 }

            // footer
            Rectangle {
                width: parent.width
                height: 52
                radius: 14
                color: "#0c1216"
                border.width: 1
                border.color: "#243038"
                Row {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8
                    Rectangle {
                        width: 120; height: 36; radius: 10
                        color: ft1.containsMouse ? "#1c262e" : "transparent"
                        Text { anchors.centerIn: parent; text: "Настройки"; color: "#d5dde3"; font.pixelSize: 12 }
                        MouseArea {
                            id: ft1; anchors.fill: parent; hoverEnabled: true
                            onClicked: { root.startOpen = false; root.launch("settings", "Настройки") }
                        }
                    }
                    Rectangle {
                        width: 140; height: 36; radius: 10
                        color: ft2.containsMouse ? "#1c262e" : "transparent"
                        Text { anchors.centerIn: parent; text: "Установка GT/OS"; color: "#d5dde3"; font.pixelSize: 12 }
                        MouseArea {
                            id: ft2; anchors.fill: parent; hoverEnabled: true
                            onClicked: { root.startOpen = false; root.launch("install", "Установка GT/OS") }
                        }
                    }
                    Item { width: parent.width - 360; height: 1 }
                    Rectangle {
                        width: 100; height: 36; radius: 10
                        color: ft3.containsMouse ? "#7f1d1d" : "#1c262e"
                        Text { anchors.centerIn: parent; text: "Выключить"; color: ft3.containsMouse ? "#fecaca" : "#e8eef2"; font.pixelSize: 12 }
                        MouseArea {
                            id: ft3; anchors.fill: parent; hoverEnabled: true
                            onClicked: { root.startOpen = false; root.powerAction("off") }
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        z: 29
        anchors.fill: parent
        visible: root.startOpen
        onClicked: root.startOpen = false
    }
'''

NOTIFICATIONS = r'''
    // тосты
    Column {
        z: 90
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 58
        anchors.rightMargin: 18
        spacing: 12
        width: 360
        visible: !root.notifyCenterOpen
        Repeater {
            model: root.notifications
            delegate: Rectangle {
                id: toast
                width: 360
                height: Math.max(72, bodyCol.height + 28)
                radius: 18
                color: "#101820"
                border.width: 1
                border.color: "#2a3842"
                clip: true
                opacity: 0
                scale: 0.92
                transformOrigin: Item.Right
                Component.onCompleted: {
                    opacity = 0.98
                    scale = 1
                }
                Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Behavior on scale { NumberAnimation { duration: 260; easing.type: Easing.OutBack } }

                Rectangle {
                    width: 4
                    height: parent.height
                    color: modelData.kind === "wifi" ? "#3b82f6" : (modelData.kind === "ok" ? root.accentColor : "#94a3b8")
                }

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    anchors.topMargin: 14
                    anchors.bottomMargin: 14
                    spacing: 12
                    Rectangle {
                        width: 40; height: 40; radius: 14
                        anchors.verticalCenter: parent.verticalCenter
                        color: modelData.kind === "wifi" ? "#1e3a5f" : (modelData.kind === "ok" ? "#14532d" : "#1f2937")
                        Text {
                            anchors.centerIn: parent
                            text: modelData.kind === "wifi" ? "◉" : (modelData.kind === "ok" ? "✓" : "i")
                            color: modelData.kind === "wifi" ? "#93c5fd" : (modelData.kind === "ok" ? "#86efac" : "#e2e8f0")
                            font.pixelSize: 16; font.bold: true
                        }
                    }
                    Column {
                        id: bodyCol
                        width: parent.width - 100
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 4
                        Text {
                            text: modelData.title
                            color: "#f8fafc"; font.pixelSize: 14; font.bold: true
                            font.family: "DejaVu Sans"; width: parent.width; elide: Text.ElideRight
                        }
                        Text {
                            text: modelData.body
                            color: "#94a3b8"; font.pixelSize: 12
                            font.family: "DejaVu Sans"; width: parent.width; wrapMode: Text.Wrap
                        }
                    }
                    Rectangle {
                        width: 28; height: 28; radius: 8
                        anchors.verticalCenter: parent.verticalCenter
                        color: xh.containsMouse ? "#243038" : "transparent"
                        Text { anchors.centerIn: parent; text: "×"; color: "#94a3b8"; font.pixelSize: 16 }
                        MouseArea {
                            id: xh; anchors.fill: parent; hoverEnabled: true
                            onClicked: root.dismissNotify(modelData.id)
                        }
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    anchors.rightMargin: 40
                    onClicked: root.notifyCenterOpen = true
                }
            }
        }
    }

    // центр уведомлений
    Rectangle {
        z: 96
        visible: root.notifyCenterOpen
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.rightMargin: 12
        anchors.topMargin: 52
        anchors.bottomMargin: root.dockSize + 28
        width: 380
        radius: 22
        color: "#0e1519"
        border.width: 1
        border.color: "#2a3842"

        Column {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            Row {
                width: parent.width
                Text {
                    text: "Уведомления"
                    color: "#f4f7f8"; font.pixelSize: 18; font.bold: true
                    font.family: "DejaVu Sans"
                    width: parent.width - 110
                    anchors.verticalCenter: parent.verticalCenter
                }
                Rectangle {
                    width: 100; height: 32; radius: 10
                    color: cl.containsMouse ? "#1c262e" : "#121a20"
                    border.width: 1; border.color: "#243038"
                    Text { anchors.centerIn: parent; text: "Очистить"; color: "#9aa7b2"; font.pixelSize: 12 }
                    MouseArea {
                        id: cl; anchors.fill: parent; hoverEnabled: true
                        onClicked: root.notifications = []
                    }
                }
            }

            Text {
                text: root.notifications.length ? (root.notifications.length + " активных") : "Пока тихо — уведомлений нет"
                color: "#7e8b96"; font.pixelSize: 12
            }

            Flickable {
                width: parent.width
                height: parent.height - 90
                clip: true
                contentHeight: nCol.height
                Column {
                    id: nCol
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: root.notifications
                        delegate: Rectangle {
                            width: nCol.width
                            height: nBody.height + 24
                            radius: 14
                            color: "#121a20"
                            border.width: 1
                            border.color: "#243038"
                            Rectangle {
                                width: 3; height: parent.height
                                color: modelData.kind === "ok" ? root.accentColor : (modelData.kind === "wifi" ? "#3b82f6" : "#64748b")
                                radius: 2
                            }
                            Column {
                                id: nBody
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 14
                                anchors.leftMargin: 14
                                spacing: 6
                                Text { text: modelData.title; color: "#f4f7f8"; font.pixelSize: 14; font.bold: true; width: parent.width; elide: Text.ElideRight }
                                Text { text: modelData.body; color: "#9aa7b2"; font.pixelSize: 12; width: parent.width; wrapMode: Text.Wrap }
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.dismissNotify(modelData.id)
                            }
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        z: 95
        anchors.fill: parent
        visible: root.notifyCenterOpen
        onClicked: root.notifyCenterOpen = false
    }
'''


def replace_block(t: str, start_marker: str, end_marker: str, new_block: str) -> str:
    a = t.find(start_marker)
    if a < 0:
        raise SystemExit(f"missing start {start_marker[:40]}")
    b = t.find(end_marker, a + 1)
    if b < 0:
        raise SystemExit(f"missing end {end_marker[:40]}")
    return t[:a] + new_block + "\n\n" + t[b:]


def main() -> None:
    t = MAIN.read_text(encoding="utf-8")
    t = theme_files(t)

    if "property bool notifyCenterOpen" not in t:
        t = t.replace(
            "    property bool quickOpen: false",
            "    property bool quickOpen: false\n    property bool notifyCenterOpen: false",
            1,
        )

    # Replace launcher: from "Rectangle {\n        id: launcher" until "Text { id: appsLabel"
    t = replace_block(
        t,
        "    Rectangle {\n        id: launcher",
        "    Text { id: appsLabel",
        LAUNCHER.strip() + "\n",
    )

    # Replace notifications: from "// уведомления" until "// первый запуск"
    t = replace_block(
        t,
        "    // уведомления",
        "    // первый запуск",
        NOTIFICATIONS.strip() + "\n",
    )

    # Clock opens notification center
    old_clock = """        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.dateLine()
            color: "#f4f7f8"
            font.pixelSize: 14
            font.family: "DejaVu Sans"
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: Qt.formatTime(root.now, "HH:mm")
            color: "#ffffff"
            font.pixelSize: 15
            font.bold: true
            font.family: "DejaVu Sans"
        }
    }"""
    new_clock = """        Item {
            width: clockRow.width + 16
            height: 36
            anchors.verticalCenter: parent.verticalCenter
            Rectangle {
                anchors.fill: parent
                radius: 10
                color: (root.notifyCenterOpen || clockHover.containsMouse) ? "#1c262e" : "transparent"
            }
            Row {
                id: clockRow
                anchors.centerIn: parent
                spacing: 10
                Text {
                    text: root.dateLine()
                    color: "#f4f7f8"
                    font.pixelSize: 14
                    font.family: "DejaVu Sans"
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: Qt.formatTime(root.now, "HH:mm")
                    color: "#ffffff"
                    font.pixelSize: 15
                    font.bold: true
                    font.family: "DejaVu Sans"
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea {
                id: clockHover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.notifyCenterOpen = !root.notifyCenterOpen
                    root.quickOpen = false
                    root.startOpen = false
                }
            }
        }
    }"""
    if old_clock in t:
        t = t.replace(old_clock, new_clock, 1)
        print("clock -> notify center")
    else:
        print("WARN: clock block not found exact")

    # close start when opening quick settings
    t = t.replace(
        "onClicked: root.quickOpen = !root.quickOpen",
        "onClicked: { root.quickOpen = !root.quickOpen; root.notifyCenterOpen = false; if (root.quickOpen) root.startOpen = false }",
        1,
    )

    MAIN.write_text(t, encoding="utf-8")
    print("patched", MAIN)


if __name__ == "__main__":
    main()
