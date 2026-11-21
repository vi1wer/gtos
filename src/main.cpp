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
    // GT Browser (Qt WebEngine): оболочка работает от root и без GPU
    qputenv("QTWEBENGINE_DISABLE_SANDBOX", "1");
    if (qEnvironmentVariableIsEmpty("QTWEBENGINE_CHROMIUM_FLAGS"))
        qputenv("QTWEBENGINE_CHROMIUM_FLAGS",
                "--no-sandbox --disable-gpu --disable-gpu-compositing --disable-dev-shm-usage "
                "--enable-features=OverlayScrollbar --num-raster-threads=2");
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);

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
