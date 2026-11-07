#include "Bridge.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>

#include <cstdio>

int main(int argc, char *argv[]) {
    qputenv("QT_QPA_PLATFORM", "xcb");
    qputenv("QT_QUICK_BACKEND", "software");
    qputenv("QSG_RHI_BACKEND", "software");
    qputenv("LIBGL_ALWAYS_SOFTWARE", "1");
    qputenv("QT_OPENGL", "software");
    qputenv("QT_XCB_GL_INTEGRATION", "none");
    qputenv("QT_QPA_FONTDIR", "/usr/share/fonts/dejavu");
    qputenv("QT_PLUGIN_PATH", "/usr/lib/qt6/plugins");
    qputenv("QML_IMPORT_PATH", "/usr/lib/qt6/qml");
    qputenv("QML2_IMPORT_PATH", "/usr/lib/qt6/qml");

    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("GT/OS"));
    app.setOrganizationName(QStringLiteral("GTOS"));

    Bridge bridge;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("sys"), &bridge);
    const QUrl mainQml(QStringLiteral("file:///usr/share/gtos/qml/Main.qml"));
    engine.load(mainQml);
    if (engine.rootObjects().isEmpty()) {
        std::fprintf(stderr, "GTOS_QML_FAIL\n");
        return 1;
    }
    std::fprintf(stderr, "GTOS_QML_OK\n");
    return app.exec();
}
