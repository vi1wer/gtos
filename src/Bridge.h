#pragma once

#include <QObject>
#include <QString>

class Bridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString kernel READ kernel NOTIFY refreshed)
    Q_PROPERTY(QString hostname READ hostname NOTIFY refreshed)
    Q_PROPERTY(QString osRelease READ osRelease NOTIFY refreshed)
    Q_PROPERTY(QString memory READ memory NOTIFY refreshed)
    Q_PROPERTY(QString uptime READ uptime NOTIFY refreshed)
    Q_PROPERTY(double cpuUsage READ cpuUsage NOTIFY refreshed)
    Q_PROPERTY(double memUsage READ memUsage NOTIFY refreshed)

public:
    explicit Bridge(QObject *parent = nullptr);

    QString kernel() const;
    QString hostname() const;
    QString osRelease() const;
    QString memory() const;
    QString uptime() const;
    double cpuUsage() const;
    double memUsage() const;

    Q_INVOKABLE void refresh();
    Q_INVOKABLE QString run(const QString &command);
    Q_INVOKABLE QString runTimeout(const QString &command, int timeoutMs);
    Q_INVOKABLE QString listDir(const QString &path);
    Q_INVOKABLE QString listDirDetailed(const QString &path);
    Q_INVOKABLE QString readFile(const QString &path);
    Q_INVOKABLE bool writeFile(const QString &path, const QString &content);
    Q_INVOKABLE QString processList();
    Q_INVOKABLE QString fetchPage(const QString &url);
    Q_INVOKABLE QString listDisks();

signals:
    void refreshed();

private:
    static QString readFileRaw(const QString &path, qint64 limit);
    static QString htmlToRichText(const QString &html);
    mutable quint64 prevTotal_ = 0;
    mutable quint64 prevIdle_ = 0;
    mutable double lastCpu_ = 0.0;
};
