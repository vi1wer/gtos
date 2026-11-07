#include "Bridge.h"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QRegularExpression>
#include <QUrl>
#include <QtGlobal>

Bridge::Bridge(QObject *parent) : QObject(parent) {}

QString Bridge::readFileRaw(const QString &path, qint64 limit) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        return {};
    }
    return QString::fromUtf8(file.read(limit));
}

QString Bridge::kernel() const { return readFileRaw(QStringLiteral("/proc/version"), 4096).trimmed(); }

QString Bridge::hostname() const { return readFileRaw(QStringLiteral("/etc/hostname"), 256).trimmed(); }

QString Bridge::osRelease() const { return readFileRaw(QStringLiteral("/etc/os-release"), 4096); }

QString Bridge::memory() const { return readFileRaw(QStringLiteral("/proc/meminfo"), 8192); }

QString Bridge::uptime() const { return readFileRaw(QStringLiteral("/proc/uptime"), 256).trimmed(); }

double Bridge::cpuUsage() const {
    const QString raw = readFileRaw(QStringLiteral("/proc/stat"), 512);
    const QString line = raw.section(QLatin1Char('\n'), 0, 0);
    if (!line.startsWith(QStringLiteral("cpu "))) {
        return lastCpu_;
    }
    const QStringList parts = line.split(QLatin1Char(' '), Qt::SkipEmptyParts);
    if (parts.size() < 5) {
        return lastCpu_;
    }
    quint64 user = parts[1].toULongLong();
    quint64 nice = parts[2].toULongLong();
    quint64 system = parts[3].toULongLong();
    quint64 idle = parts[4].toULongLong();
    quint64 iowait = parts.size() > 5 ? parts[5].toULongLong() : 0;
    quint64 irq = parts.size() > 6 ? parts[6].toULongLong() : 0;
    quint64 softirq = parts.size() > 7 ? parts[7].toULongLong() : 0;
    const quint64 idleAll = idle + iowait;
    const quint64 total = user + nice + system + idleAll + irq + softirq;
    if (prevTotal_ > 0 && total > prevTotal_) {
        const double totalDelta = double(total - prevTotal_);
        const double idleDelta = double(idleAll - prevIdle_);
        lastCpu_ = qBound(0.0, 100.0, 100.0 * (1.0 - idleDelta / totalDelta));
    }
    prevTotal_ = total;
    prevIdle_ = idleAll;
    return lastCpu_;
}

double Bridge::memUsage() const {
    const QString raw = memory();
    qint64 total = 0;
    qint64 available = 0;
    const QStringList lines = raw.split(QLatin1Char('\n'));
    for (const QString &line : lines) {
        if (line.startsWith(QStringLiteral("MemTotal:"))) {
            total = line.split(QLatin1Char(' '), Qt::SkipEmptyParts).value(1).toLongLong();
        } else if (line.startsWith(QStringLiteral("MemAvailable:"))) {
            available = line.split(QLatin1Char(' '), Qt::SkipEmptyParts).value(1).toLongLong();
        }
    }
    if (total <= 0) {
        return 0.0;
    }
    if (available <= 0) {
        qint64 free = 0;
        qint64 buffers = 0;
        qint64 cached = 0;
        for (const QString &line : lines) {
            if (line.startsWith(QStringLiteral("MemFree:")))
                free = line.split(QLatin1Char(' '), Qt::SkipEmptyParts).value(1).toLongLong();
            else if (line.startsWith(QStringLiteral("Buffers:")))
                buffers = line.split(QLatin1Char(' '), Qt::SkipEmptyParts).value(1).toLongLong();
            else if (line.startsWith(QStringLiteral("Cached:")))
                cached = line.split(QLatin1Char(' '), Qt::SkipEmptyParts).value(1).toLongLong();
        }
        available = free + buffers + cached;
    }
    return qBound(0.0, 100.0, 100.0 * double(total - available) / double(total));
}

void Bridge::refresh() { emit refreshed(); }

QString Bridge::run(const QString &command) {
    return runTimeout(command, 4000);
}

QString Bridge::runTimeout(const QString &command, int timeoutMs) {
    const QString trimmed = command.trimmed();
    if (trimmed.isEmpty()) {
        return {};
    }
    const int ms = timeoutMs > 0 ? timeoutMs : 4000;
    QProcess process;
    process.start(QStringLiteral("/bin/sh"), {QStringLiteral("-c"), trimmed});
    if (!process.waitForStarted(1500)) {
        return QStringLiteral("не удалось запустить /bin/sh\n");
    }
    // UI вызывает run синхронно — длинный wait = «зависла вся ОС»
    if (!process.waitForFinished(ms)) {
        process.kill();
        process.waitForFinished(500);
        return QStringLiteral("таймаут\n");
    }
    return QString::fromUtf8(process.readAllStandardOutput() + process.readAllStandardError());
}

QString Bridge::listDir(const QString &path) {
    QDir dir(path);
    if (!dir.exists()) {
        return {};
    }
    QStringList lines;
    const auto entries = dir.entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot, QDir::DirsFirst | QDir::Name);
    for (const QFileInfo &info : entries) {
        lines << (info.isDir() ? QStringLiteral("[dir] ") : QStringLiteral("[file] ")) + info.fileName();
    }
    return lines.join(QLatin1Char('\n'));
}

QString Bridge::readFile(const QString &path) { return readFileRaw(path, 65536); }

bool Bridge::writeFile(const QString &path, const QString &content) {
    QFileInfo info(path);
    QDir().mkpath(info.absolutePath());
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        return false;
    }
    const QByteArray data = content.toUtf8();
    return file.write(data) == data.size();
}

QString Bridge::processList() {
    QProcess process;
    process.start(QStringLiteral("/bin/sh"),
                  {QStringLiteral("-c"),
                   QStringLiteral("busybox ps w 2>/dev/null | busybox head -n 25")});
    if (!process.waitForFinished(4000)) {
        return QStringLiteral("нет данных");
    }
    return QString::fromUtf8(process.readAllStandardOutput()).trimmed();
}

QString Bridge::listDirDetailed(const QString &path) {
    QDir dir(path);
    if (!dir.exists()) {
        return {};
    }
    QStringList lines;
    const auto entries = dir.entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot, QDir::DirsFirst | QDir::Name);
    for (const QFileInfo &info : entries) {
        const QString kind = info.isDir() ? QStringLiteral("dir") : QStringLiteral("file");
        QString type = info.isDir() ? QStringLiteral("Папка с файлами") : QStringLiteral("Файл");
        if (!info.isDir()) {
            const QString suf = info.suffix().toLower();
            if (suf == QLatin1String("txt") || suf == QLatin1String("md") || suf == QLatin1String("log"))
                type = QStringLiteral("Текстовый документ");
            else if (suf == QLatin1String("jpg") || suf == QLatin1String("jpeg") || suf == QLatin1String("png")
                     || suf == QLatin1String("webp") || suf == QLatin1String("gif"))
                type = QStringLiteral("Изображение");
            else if (suf == QLatin1String("mp3") || suf == QLatin1String("wav") || suf == QLatin1String("ogg"))
                type = QStringLiteral("Аудио");
            else if (suf == QLatin1String("mp4") || suf == QLatin1String("mkv") || suf == QLatin1String("webm"))
                type = QStringLiteral("Видео");
            else if (suf == QLatin1String("sh") || suf == QLatin1String("py"))
                type = QStringLiteral("Сценарий");
            else if (!suf.isEmpty())
                type = suf.toUpper() + QStringLiteral("-файл");
        }
        const QString mtime = info.lastModified().toString(QStringLiteral("dd.MM.yyyy HH:mm"));
        const qint64 size = info.isDir() ? 0 : info.size();
        lines << kind + QLatin1Char('\t') + info.fileName() + QLatin1Char('\t') + QString::number(size)
                     + QLatin1Char('\t') + mtime + QLatin1Char('\t') + type;
    }
    return lines.join(QLatin1Char('\n'));
}

static QString decodeHtmlEntities(QString s) {
    s.replace(QStringLiteral("&nbsp;"), QStringLiteral(" "));
    s.replace(QStringLiteral("&amp;"), QStringLiteral("&"));
    s.replace(QStringLiteral("&lt;"), QStringLiteral("<"));
    s.replace(QStringLiteral("&gt;"), QStringLiteral(">"));
    s.replace(QStringLiteral("&quot;"), QStringLiteral("\""));
    s.replace(QStringLiteral("&apos;"), QStringLiteral("'"));
    s.replace(QStringLiteral("&mdash;"), QStringLiteral("—"));
    s.replace(QStringLiteral("&ndash;"), QStringLiteral("–"));
    s.replace(QStringLiteral("&hellip;"), QStringLiteral("…"));
    s.replace(QStringLiteral("&copy;"), QStringLiteral("©"));
    s.replace(QStringLiteral("&reg;"), QStringLiteral("®"));
    s.replace(QStringLiteral("&bull;"), QStringLiteral("•"));
    QRegularExpression dec(QStringLiteral("&#(\\d+);"));
    QRegularExpressionMatchIterator it = dec.globalMatch(s);
    QString out;
    out.reserve(s.size());
    int last = 0;
    while (it.hasNext()) {
        const QRegularExpressionMatch m = it.next();
        out += s.mid(last, m.capturedStart() - last);
        out += QChar(m.captured(1).toInt());
        last = m.capturedEnd();
    }
    out += s.mid(last);
    s = out;
    QRegularExpression hex(QStringLiteral("&#x([0-9a-fA-F]+);"));
    it = hex.globalMatch(s);
    out.clear();
    last = 0;
    while (it.hasNext()) {
        const QRegularExpressionMatch m = it.next();
        out += s.mid(last, m.capturedStart() - last);
        out += QChar(m.captured(1).toInt(nullptr, 16));
        last = m.capturedEnd();
    }
    out += s.mid(last);
    return out;
}

static QString wrapBrowserPage(const QString &inner) {
    return QStringLiteral(
               "<body style=\"font-family:'Montserrat','Sora','Segoe UI',sans-serif;font-size:15px;"
               "line-height:1.6;color:#202124;background:#ffffff;margin:0;padding:8px 4px;\">"
               "<div style=\"max-width:920px;margin:0 auto;\">")
           + inner + QStringLiteral("</div></body>");
}

static QString googleHomePage() {
    return wrapBrowserPage(QStringLiteral(
        "<div align=\"center\" style=\"padding:48px 16px 24px 16px;\">"
        "<p style=\"font-size:64px;font-weight:700;letter-spacing:-2px;margin:0;\">"
        "<span style=\"color:#4285F4;\">G</span>"
        "<span style=\"color:#EA4335;\">o</span>"
        "<span style=\"color:#FBBC05;\">o</span>"
        "<span style=\"color:#4285F4;\">g</span>"
        "<span style=\"color:#34A853;\">l</span>"
        "<span style=\"color:#EA4335;\">e</span>"
        "</p>"
        "<p style=\"color:#5f6368;font-size:14px;margin:18px 0 28px 0;\">"
        "Упрощённый вид GT/OS Browser — без JavaScript.<br/>"
        "Введите запрос в строке «Поиск» выше или откройте ссылку."
        "</p>"
        "<p style=\"font-size:15px;margin:12px 0;\">"
        "<a href=\"https://mail.google.com\" style=\"color:#1a73e8;text-decoration:none;\">Почта</a>"
        "&nbsp;&nbsp;&nbsp;"
        "<a href=\"https://www.google.com/imghp\" style=\"color:#1a73e8;text-decoration:none;\">Картинки</a>"
        "&nbsp;&nbsp;&nbsp;"
        "<a href=\"https://accounts.google.com\" style=\"color:#1a73e8;text-decoration:none;\">Войти</a>"
        "</p>"
        "<p style=\"margin-top:36px;\">"
        "<a href=\"https://www.google.com/search?q=GT%2FOS\" style=\"color:#1a73e8;\">Найти GT/OS</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://www.google.com/advanced_search\" style=\"color:#1a73e8;\">Расширенный поиск</a>"
        "</p>"
        "<p style=\"color:#70757a;font-size:12px;margin-top:48px;\">"
        "<a href=\"https://www.google.ru/intl/ru/ads\" style=\"color:#70757a;\">Реклама</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://www.google.ru/services\" style=\"color:#70757a;\">Для бизнеса</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://about.google\" style=\"color:#70757a;\">Всё о Google</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://policies.google.com/privacy\" style=\"color:#70757a;\">Конфиденциальность</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://policies.google.com/terms\" style=\"color:#70757a;\">Условия</a>"
        "</p>"
        "</div>"));
}

static QString yandexHomePage() {
    return wrapBrowserPage(QStringLiteral(
        "<div align=\"center\" style=\"padding:48px 16px;\">"
        "<h1 style=\"color:#fc0;background:#000;display:inline;padding:4px 14px;"
        "font-size:42px;border-radius:8px;\">Яндекс</h1>"
        "<p style=\"color:#5f6368;margin:24px 0;\">Упрощённый вид. Используйте строку «Поиск» выше.</p>"
        "<p>"
        "<a href=\"https://mail.yandex.ru\" style=\"color:#06c;\">Почта</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://yandex.ru/images\" style=\"color:#06c;\">Картинки</a>"
        "&nbsp;·&nbsp;"
        "<a href=\"https://yandex.ru/maps\" style=\"color:#06c;\">Карты</a>"
        "</p>"
        "</div>"));
}

static bool isBareSearchHome(const QUrl &u) {
    const QString host = u.host().toLower();
    QString path = u.path();
    if (path.isEmpty())
        path = QStringLiteral("/");
    const bool bare = (path == QLatin1String("/") || path == QLatin1String("/webhp")
                       || path == QLatin1String("/imghp"));
    if (!bare)
        return false;
    if (host == QLatin1String("google.com") || host == QLatin1String("www.google.com")
        || host == QLatin1String("google.ru") || host == QLatin1String("www.google.ru")
        || host.endsWith(QLatin1String(".google.com")))
        return true;
    if (host == QLatin1String("yandex.ru") || host == QLatin1String("www.yandex.ru")
        || host == QLatin1String("ya.ru"))
        return true;
    return false;
}

QString Bridge::htmlToRichText(const QString &html) {
    QString body = html;
    const int bodyOpen = body.indexOf(QStringLiteral("<body"), 0, Qt::CaseInsensitive);
    if (bodyOpen >= 0) {
        const int gt = body.indexOf(QLatin1Char('>'), bodyOpen);
        const int bodyClose = body.indexOf(QStringLiteral("</body>"), gt, Qt::CaseInsensitive);
        if (gt >= 0 && bodyClose > gt)
            body = body.mid(gt + 1, bodyClose - gt - 1);
    }

    body.remove(QRegularExpression(QStringLiteral("<!--[\\s\\S]*?-->")));
    body.remove(QRegularExpression(QStringLiteral("<script[^>]*>[\\s\\S]*?</script>"),
                                   QRegularExpression::CaseInsensitiveOption));
    // оставляем полезные куски из style как подсказки через data, но сами блоки style убираем
    body.remove(QRegularExpression(QStringLiteral("<style[^>]*>[\\s\\S]*?</style>"),
                                   QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<noscript[^>]*>[\\s\\S]*?</noscript>"),
                                   QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<svg[^>]*>[\\s\\S]*?</svg>"),
                                   QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<iframe[^>]*>[\\s\\S]*?</iframe>"),
                                   QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<template[^>]*>[\\s\\S]*?</template>"),
                                   QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<link[^>]*>"), QRegularExpression::CaseInsensitiveOption));
    body.remove(QRegularExpression(QStringLiteral("<meta[^>]*>"), QRegularExpression::CaseInsensitiveOption));

    // img → подпись из alt
    body.replace(QRegularExpression(QStringLiteral("<img[^>]*alt=[\"']([^\"']+)[\"'][^>]*>"),
                                   QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<span style=\"color:#5f6368;font-size:12px;\">[изображение: \\1]</span>"));
    body.replace(QRegularExpression(QStringLiteral("<img[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QString());

    // структурные теги Qt Rich Text с лёгким CSS
    body.replace(QRegularExpression(QStringLiteral("<h1[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<h1 style=\"font-size:28px;font-weight:700;color:#202124;margin:16px 0 8px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("<h2[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<h2 style=\"font-size:22px;font-weight:700;color:#202124;margin:14px 0 6px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("<h3[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<h3 style=\"font-size:18px;font-weight:600;color:#1a0dab;margin:12px 0 4px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("<h4[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<h3 style=\"font-size:16px;font-weight:600;color:#202124;\">"));
    body.replace(QRegularExpression(QStringLiteral("</h4\\s*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("</h3>"));
    body.replace(QRegularExpression(QStringLiteral("<p[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<p style=\"margin:0 0 10px 0;line-height:1.6;\">"));
    body.replace(QRegularExpression(QStringLiteral("<blockquote[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<blockquote style=\"border-left:3px solid #dadce0;margin:10px 0;padding:4px 12px;color:#5f6368;\">"));
    body.replace(QRegularExpression(QStringLiteral("<pre[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<pre style=\"background:#f8f9fa;border:1px solid #dadce0;border-radius:8px;padding:10px;"
                                "font-family:Cascadia Mono,monospace;font-size:13px;\">"));
    body.replace(QRegularExpression(QStringLiteral("<code[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<code style=\"background:#f1f3f4;padding:1px 5px;border-radius:4px;"
                                "font-family:Cascadia Mono,monospace;font-size:13px;\">"));
    body.replace(QRegularExpression(QStringLiteral("<hr\\s*/?>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<hr style=\"border:none;border-top:1px solid #dadce0;margin:16px 0;\"/>"));
    body.replace(QRegularExpression(QStringLiteral("<ul[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<ul style=\"margin:8px 0 8px 18px;\">"));
    body.replace(QRegularExpression(QStringLiteral("<ol[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<ol style=\"margin:8px 0 8px 18px;\">"));
    body.replace(QRegularExpression(QStringLiteral("<li[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<li style=\"margin:3px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("<table[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<table border=\"0\" cellspacing=\"0\" cellpadding=\"6\" "
                                "style=\"border-collapse:collapse;margin:10px 0;width:100%;\">"));
    body.replace(QRegularExpression(QStringLiteral("<(td|th)[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<\\1 style=\"border-bottom:1px solid #e8eaed;padding:6px 8px;text-align:left;\">"));
    body.replace(QRegularExpression(QStringLiteral("<div[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<div style=\"margin:4px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("<(section|article|main|header|footer|nav|aside)[^>]*>"),
                                   QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<div style=\"margin:8px 0;\">"));
    body.replace(QRegularExpression(QStringLiteral("</(section|article|main|header|footer|nav|aside)\\s*>"),
                                   QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("</div>"));
    body.replace(QRegularExpression(QStringLiteral("<span[^>]*>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<span>"));
    body.replace(QRegularExpression(QStringLiteral("<br\\s*/?>"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<br/>"));

    // ссылки
    body.replace(QRegularExpression(QStringLiteral("</a\\s*>\\s*<a\\s"), QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a "));
    body.replace(QRegularExpression(QStringLiteral("<a\\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>"),
                                   QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("<a href=\"\\1\" style=\"color:#1a0dab;text-decoration:none;\">"));

    // убрать on* и javascript:
    body.replace(QRegularExpression(QStringLiteral("\\s+on[a-z]+=\"[^\"]*\""), QRegularExpression::CaseInsensitiveOption),
                 QString());
    body.replace(QRegularExpression(QStringLiteral("\\s+on[a-z]+='[^']*'"), QRegularExpression::CaseInsensitiveOption),
                 QString());
    body.replace(QRegularExpression(QStringLiteral("href=[\"']javascript:[^\"']*[\"']"),
                                   QRegularExpression::CaseInsensitiveOption),
                 QStringLiteral("href=\"#\""));

    QString out;
    out.reserve(body.size());
    bool inTag = false;
    QString tag;
    for (int i = 0; i < body.size(); ++i) {
        const QChar ch = body.at(i);
        if (ch == QLatin1Char('<')) {
            inTag = true;
            tag.clear();
            continue;
        }
        if (ch == QLatin1Char('>') && inTag) {
            inTag = false;
            const QString t = tag.toLower();
            const QString name = t.section(QLatin1Char(' '), 0, 0);
            static const QStringList keep = {
                QStringLiteral("br"), QStringLiteral("br/"), QStringLiteral("hr"), QStringLiteral("hr/"),
                QStringLiteral("b"), QStringLiteral("/b"), QStringLiteral("i"), QStringLiteral("/i"),
                QStringLiteral("u"), QStringLiteral("/u"), QStringLiteral("s"), QStringLiteral("/s"),
                QStringLiteral("strong"), QStringLiteral("/strong"), QStringLiteral("em"), QStringLiteral("/em"),
                QStringLiteral("h1"), QStringLiteral("/h1"), QStringLiteral("h2"), QStringLiteral("/h2"),
                QStringLiteral("h3"), QStringLiteral("/h3"), QStringLiteral("p"), QStringLiteral("/p"),
                QStringLiteral("div"), QStringLiteral("/div"), QStringLiteral("span"), QStringLiteral("/span"),
                QStringLiteral("ul"), QStringLiteral("/ul"), QStringLiteral("ol"), QStringLiteral("/ol"),
                QStringLiteral("li"), QStringLiteral("/li"), QStringLiteral("blockquote"), QStringLiteral("/blockquote"),
                QStringLiteral("pre"), QStringLiteral("/pre"), QStringLiteral("code"), QStringLiteral("/code"),
                QStringLiteral("table"), QStringLiteral("/table"), QStringLiteral("tr"), QStringLiteral("/tr"),
                QStringLiteral("td"), QStringLiteral("/td"), QStringLiteral("th"), QStringLiteral("/th"),
                QStringLiteral("thead"), QStringLiteral("/thead"), QStringLiteral("tbody"), QStringLiteral("/tbody"),
                QStringLiteral("/a")};
            if (keep.contains(name) || name.startsWith(QLatin1String("a href")) || name.startsWith(QLatin1String("a ")))
                out += QLatin1Char('<') + tag + QLatin1Char('>');
            continue;
        }
        if (inTag) {
            tag += ch;
            continue;
        }
        out += ch;
    }

    out = decodeHtmlEntities(out);
    out.replace(QRegularExpression(QStringLiteral("(\\s*<br/>\\s*){3,}")), QStringLiteral("<br/><br/>"));
    out.replace(QRegularExpression(QStringLiteral("[ \\t\\x0b\\f\\r]+")), QStringLiteral(" "));
    out = out.trimmed();
    if (out.size() > 120000)
        out = out.left(120000) + QStringLiteral("<br/><br/><i>… страница обрезана</i>");
    if (out.isEmpty())
        return wrapBrowserPage(QStringLiteral(
            "<p style=\"color:#5f6368;padding:24px;\">На странице нет текстового содержимого "
            "(часто так бывает у сайтов только на JavaScript).</p>"
            "<p style=\"padding:0 24px;\"><i>Попробуйте поиск выше или другой адрес.</i></p>"));
    return wrapBrowserPage(out);
}

QString Bridge::fetchPage(const QString &url) {
    QString u = url.trimmed();
    if (u.isEmpty())
        return wrapBrowserPage(QStringLiteral("<i>Пустой адрес</i>"));
    if (!u.startsWith(QLatin1String("http://")) && !u.startsWith(QLatin1String("https://")))
        u.prepend(QStringLiteral("https://"));

    const QUrl parsed(u);
    if (isBareSearchHome(parsed)) {
        const QString host = parsed.host().toLower();
        if (host.contains(QLatin1String("yandex")) || host == QLatin1String("ya.ru"))
            return yandexHomePage();
        return googleHomePage();
    }

    QProcess process;
    process.start(QStringLiteral("/bin/sh"),
                  {QStringLiteral("-c"),
                   QStringLiteral("curl -fsSL --max-time 12 -L -A 'Mozilla/5.0 (X11; Linux x86_64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                                  "GTOS-Browser/1.4' ")
                       + QLatin1Char('\'') + u.replace(QLatin1Char('\''), QStringLiteral("'\\''"))
                       + QLatin1Char('\'')});
    if (!process.waitForStarted(1500))
        return wrapBrowserPage(QStringLiteral("<b>Не удалось запустить curl</b>"));
    if (!process.waitForFinished(15000)) {
        process.kill();
        return wrapBrowserPage(QStringLiteral("<b>Таймаут загрузки</b>"));
    }
    const QByteArray raw = process.readAllStandardOutput();
    const QByteArray err = process.readAllStandardError();
    if (raw.isEmpty()) {
        const QString e = QString::fromUtf8(err).trimmed();
        return wrapBrowserPage(QStringLiteral("<b>Не удалось открыть страницу</b><br/>")
                               + e.toHtmlEscaped());
    }
    return htmlToRichText(QString::fromUtf8(raw));
}

QString Bridge::listDisks() {
    QProcess process;
    process.start(QStringLiteral("/bin/sh"),
                  {QStringLiteral("-c"),
                   QStringLiteral("lsblk -dn -o NAME,SIZE,TYPE,MODEL,TRAN 2>/dev/null | awk '$3==\"disk\"{print}'")});
    if (!process.waitForFinished(5000))
        return {};
    return QString::fromUtf8(process.readAllStandardOutput()).trimmed();
}
