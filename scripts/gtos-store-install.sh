#!/bin/sh
# GT/OS Store installer: alpine | linux (AppImage/deb/tar) | windows (Wine)
set -eu

REPAIR_ID=""
if [ "${1:-}" = "--repair-appimage" ]; then
    REPAIR_ID="${2:-}"
    [ -n "$REPAIR_ID" ] || { echo "usage: gtos-store-install --repair-appimage <id>" >&2; exit 2; }
fi

JOB="${1:-/tmp/gtos-store-job.env}"
LOG="${GTOS_STORE_LOG:-/tmp/gtos-apk-log}"
RC_FILE="${GTOS_STORE_RC:-/tmp/gtos-store-rc}"
DONE_FILE="${GTOS_STORE_DONE:-/tmp/gtos-store-done}"
URL_FILE="${GTOS_STORE_URL:-/tmp/gtos-store-url.txt}"
if [ -n "$REPAIR_ID" ]; then
    LOG="${GTOS_STORE_LOG:-/tmp/gtos-repair-$REPAIR_ID.log}"
fi

# /tmp/gtos-store-expect не трогаем: его пишет оболочка из каталога (размер для шкалы)
rm -f "$DONE_FILE" "$RC_FILE" /tmp/gtos-store-phase /tmp/gtos-store-bytes \
    /tmp/gtos-store-speed /tmp/gtos-store-label /tmp/gtos-store-eta
: >"$LOG"
echo "GTOS_STORE_INSTALL start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"
echo "prepare" >/tmp/gtos-store-phase
echo "Подготовка…" >/tmp/gtos-store-label
echo 0 >/tmp/gtos-store-bytes
# ранний heartbeat — чтобы UI не залипал на 8% пока ждём сеть/apk
(
    n=0
    while [ "$n" -lt 120 ]; do
        ph=$(cat /tmp/gtos-store-phase 2>/dev/null || echo prepare)
        case "$ph" in
            download|extract|apk|done|error) break ;;
        esac
        echo "$((n * 512 * 1024))" >/tmp/gtos-store-bytes
        # не затирать фазу, если основной скрипт уже продвинулся
        ph2=$(cat /tmp/gtos-store-phase 2>/dev/null || echo prepare)
        case "$ph2" in
            download|extract|apk|done|error) break ;;
            *) echo "prepare" >/tmp/gtos-store-phase
               echo "Подготовка… ${n}с" >/tmp/gtos-store-label ;;
        esac
        n=$((n + 1))
        sleep 1
    done
) &
PREP_HB=$!
kill_prep_hb() { kill "$PREP_HB" 2>/dev/null || true; wait "$PREP_HB" 2>/dev/null || true; }

fail() {
    code="${1:-1}"
    msg="${2:-install failed}"
    kill_prep_hb 2>/dev/null || true
    echo "ERROR: $msg" >>"$LOG"
    echo "error" >/tmp/gtos-store-phase
    echo "$msg" >/tmp/gtos-store-label
    echo "$code" >"$RC_FILE"
    # совместимость со старым таймером оболочки
    echo "$code" >/tmp/gtos-apk-rc
    echo done >"$DONE_FILE"
    echo done >/tmp/gtos-apk-done
    exit 0
}

ok_done() {
    kill_prep_hb 2>/dev/null || true
    echo "done" >/tmp/gtos-store-phase
    echo "Готово" >/tmp/gtos-store-label
    echo 0 >"$RC_FILE"
    echo 0 >/tmp/gtos-apk-rc
    echo done >"$DONE_FILE"
    echo done >/tmp/gtos-apk-done
    echo "GTOS_STORE_INSTALL ok" >>"$LOG"
    exit 0
}

set_phase() {
    echo "$1" >/tmp/gtos-store-phase
    case "$1" in
        download) echo "Загрузка…" >/tmp/gtos-store-label ;;
        extract) echo "Распаковка…" >/tmp/gtos-store-label ;;
        apk) echo "Установка пакета…" >/tmp/gtos-store-label ;;
        prepare) echo "Подготовка…" >/tmp/gtos-store-label ;;
    esac
}

CURL_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 GTOS-Store/1.6"

if [ -z "$REPAIR_ID" ]; then
    [ -f "$JOB" ] || fail 2 "нет файла задания $JOB"
fi

ID=""
SOURCE="alpine"
APK=""
NAME=""
FORMAT=""
BIN=""
EXE=""
BRANCH="v3.24"
URL=""
if [ -n "$REPAIR_ID" ]; then
    ID=$REPAIR_ID
    SOURCE=linux
    FORMAT=appimage
    NAME=$REPAIR_ID
else
    # shellcheck disable=SC1090
    . "$JOB"
    ID="${ID:-}"
    SOURCE="${SOURCE:-alpine}"
    APK="${APK:-$ID}"
    NAME="${NAME:-$ID}"
    FORMAT="${FORMAT:-}"
    BIN="${BIN:-}"
    EXE="${EXE:-}"
    BRANCH="${BRANCH:-v3.24}"
    if [ -f "$URL_FILE" ]; then
        URL=$(tr -d '\r' <"$URL_FILE" | head -n 1)
    fi
    URL="${URL:-${APP_URL:-}}"
fi

[ -n "$ID" ] || fail 2 "пустой ID"

ROOT="/var/lib/gtos/apps/$ID"
mkdir -p "$ROOT/bin" "$ROOT/dl" /var/lib/gtos/apk-cache /etc/apk
USER_NAME="${GTOS_USER:-misha}"

write_launcher() {
    body="$1"
    # Только LF: CRLF в shebang → «Exec format error» у su-exec
    body=$(printf '%s' "$body" | tr -d '\r')
    {
        printf '%s\n' '#!/bin/sh'
        printf '%s\n' "$body"
    } >"$ROOT/bin/launch"
    # на всякий случай ещё раз вычистить CR
    tr -d '\r' <"$ROOT/bin/launch" >"$ROOT/bin/launch.tmp" && mv -f "$ROOT/bin/launch.tmp" "$ROOT/bin/launch"
    chmod 755 "$ROOT/bin/launch"
    # проверка: должен быть текстовый скрипт, не ELF
    if head -c 4 "$ROOT/bin/launch" | grep -q 'ELF'; then
        echo "ERROR: launch стал ELF — перезапись" >>"$LOG"
        printf '%s\n' '#!/bin/sh' 'echo "broken launcher" >&2' 'exit 1' >"$ROOT/bin/launch"
        chmod 755 "$ROOT/bin/launch"
    fi
}

ensure_wine() {
    if command -v wine >/dev/null 2>&1; then
        return 0
    fi
    echo "installing wine…" >>"$LOG"
    printf '%s\n' \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/main" \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/community" \
        >/etc/apk/repositories
    apk update --cache-dir /var/lib/gtos/apk-cache >>"$LOG" 2>&1 || true
    apk add --no-progress --cache-dir /var/lib/gtos/apk-cache wine >>"$LOG" 2>&1 \
        || apk add --no-progress --cache-dir /var/lib/gtos/apk-cache wine-staging >>"$LOG" 2>&1 \
        || return 1
    command -v wine >/dev/null 2>&1
}

probe_expect_size() {
    [ -n "$URL" ] || return 0
    command -v curl >/dev/null 2>&1 || return 0
    # короткий HEAD — длинный таймаут раньше выглядел как «залипло на 8%»
    exp=$(curl -fsSIL -A "$CURL_UA" --connect-timeout 8 --max-time 12 "$URL" 2>/dev/null \
        | awk 'BEGIN{IGNORECASE=1} /^content-length:/{print $2}' | tr -d '\r' | tail -n 1)
    # HEAD на редиректе иногда отдаёт размер HTML-страницы — не верим крошечным ответам
    if [ -n "$exp" ] && [ "$exp" -gt 100000 ] 2>/dev/null; then
        echo "$exp" >/tmp/gtos-store-expect
        echo "expect bytes=$exp" >>"$LOG"
    fi
}

download() {
    dest="$1"
    min_bytes="${2:-100000}"
    [ -n "$URL" ] || return 1
    kill_prep_hb 2>/dev/null || true
    set_phase download
    echo "download $URL -> $dest (min=$min_bytes)" >>"$LOG"
    probe_expect_size || true
    rm -f "$dest"
    if command -v curl >/dev/null 2>&1; then
        (
            prev=0
            prev_t=$(date +%s 2>/dev/null || echo 0)
            while :; do
                if [ -f "$dest" ]; then
                    sz=$(stat -c%s "$dest" 2>/dev/null || echo 0)
                    echo "$sz" >/tmp/gtos-store-bytes
                    now=$(date +%s 2>/dev/null || echo 0)
                    dt=$((now - prev_t))
                    if [ "$dt" -ge 1 ] 2>/dev/null; then
                        spd=$(( (sz - prev) / dt ))
                        [ "$spd" -lt 0 ] && spd=0
                        echo "$spd" >/tmp/gtos-store-speed
                        exp=$(cat /tmp/gtos-store-expect 2>/dev/null || echo 0)
                        if [ "$exp" -gt 0 ] 2>/dev/null && [ "$spd" -gt 0 ] 2>/dev/null; then
                            left=$((exp - sz))
                            [ "$left" -lt 0 ] && left=0
                            eta=$((left / spd))
                            echo "$eta" >/tmp/gtos-store-eta
                            mb=$((sz / 1048576))
                            emb=$((exp / 1048576))
                            sm=$((spd / 1024))
                            echo "Загрузка ${mb}/${emb} МБ · ${sm} КБ/с · ~${eta}с" >/tmp/gtos-store-label
                        else
                            mb=$((sz / 1048576))
                            sm=$((spd / 1024))
                            echo "Загрузка ${mb} МБ · ${sm} КБ/с" >/tmp/gtos-store-label
                        fi
                        prev=$sz
                        prev_t=$now
                    fi
                else
                    echo "Соединение с сервером…" >/tmp/gtos-store-label
                fi
                sleep 1
            done
        ) &
        watch_pid=$!
        if curl -fL -A "$CURL_UA" --retry 4 --retry-delay 2 --retry-all-errors \
            --connect-timeout 25 --max-time 3600 \
            -o "$dest" "$URL" >>"$LOG" 2>&1; then
            kill "$watch_pid" 2>/dev/null || true
            wait "$watch_pid" 2>/dev/null || true
            sz=$(stat -c%s "$dest" 2>/dev/null || echo 0)
            echo "$sz" >/tmp/gtos-store-bytes
            echo 0 >/tmp/gtos-store-speed
            echo "Скачано $((sz / 1048576)) МБ" >/tmp/gtos-store-label
            [ "$sz" -gt "$min_bytes" ] 2>/dev/null || return 1
            return 0
        fi
        kill "$watch_pid" 2>/dev/null || true
        wait "$watch_pid" 2>/dev/null || true
        return 1
    elif command -v wget >/dev/null 2>&1; then
        wget -U "$CURL_UA" -O "$dest" "$URL" >>"$LOG" 2>&1 || return 1
        sz=$(stat -c%s "$dest" 2>/dev/null || echo 0)
        echo "$sz" >/tmp/gtos-store-bytes
        [ "$sz" -gt "$min_bytes" ] 2>/dev/null || return 1
        return 0
    else
        return 1
    fi
}

# Проверка кандидата: в ELF runtime часто есть ложные «hsqs».
# Настоящий squashfs — major=4, block_size степень 2, bytes_used ≈ размер хвоста.
squashfs_hdr_ok() {
    img="$1"
    off="$2"
    size="$3"
    # major at +28 (u16 le), block_size at +12 (u32 le), bytes_used at +40 (u64 le)
    # busybox od часто без -tu8 — читаем два u32
    maj=$(dd if="$img" bs=1 skip=$((off + 28)) count=2 2>/dev/null | od -An -tu2 | awk '{print $1; exit}')
    [ "$maj" = "4" ] || return 1
    blksz=$(dd if="$img" bs=1 skip=$((off + 12)) count=4 2>/dev/null | od -An -tu4 | awk '{print $1; exit}')
    case "$blksz" in
        4096|8192|16384|32768|65536|131072) ;;
        *) return 1 ;;
    esac
    lo=$(dd if="$img" bs=1 skip=$((off + 40)) count=4 2>/dev/null | od -An -tu4 | awk '{print $1; exit}')
    hi=$(dd if="$img" bs=1 skip=$((off + 44)) count=4 2>/dev/null | od -An -tu4 | awk '{print $1; exit}')
    [ -n "$lo" ] && [ -n "$hi" ] || return 1
    # shell arithmetic: used = lo + hi*2^32 (hi обычно 0 для <4ГБ)
    used=$((lo + hi * 4294967296))
    remain=$((size - off))
    diff=$((used - remain))
    [ "$diff" -lt 0 ] && diff=$((0 - diff))
    [ "$diff" -lt 1048576 ] || return 1
    return 0
}

# Ищем магию squashfs (hsqs) кусками — НИКОГДА не grep по всему 300+ МБ файлу.
# Берём НЕ первый hit: в runtime Cursor/Electron ложный hsqs раньше настоящего.
find_squashfs_offset() {
    img="$1"
    size=$(stat -c%s "$img" 2>/dev/null || echo 0)
    [ "$size" -gt 0 ] || return 1
    bs=1048576
    max_scan=8388608
    [ "$max_scan" -gt "$size" ] && max_scan=$size
    off=0
    while [ "$off" -lt "$max_scan" ]; do
        # все вхождения в мегабайтном куске (не только первое)
        hits=$(dd if="$img" bs="$bs" skip=$((off / bs)) count=1 2>/dev/null | LC_ALL=C grep -aob hsqs | cut -d: -f1 || true)
        for chunk in $hits; do
            cand=$((off + chunk))
            if squashfs_hdr_ok "$img" "$cand" "$size"; then
                echo "$cand"
                return 0
            fi
            echo "skip false hsqs @$cand" >>"$LOG"
        done
        off=$((off + bs))
    done
    # запас: дальше до 32 МБ
    max_scan=33554432
    [ "$max_scan" -gt "$size" ] && max_scan=$size
    while [ "$off" -lt "$max_scan" ]; do
        hits=$(dd if="$img" bs="$bs" skip=$((off / bs)) count=1 2>/dev/null | LC_ALL=C grep -aob hsqs | cut -d: -f1 || true)
        for chunk in $hits; do
            cand=$((off + chunk))
            if squashfs_hdr_ok "$img" "$cand" "$size"; then
                echo "$cand"
                return 0
            fi
        done
        off=$((off + bs))
    done
    return 1
}

# Alpine/musl: runtime AppImage (glibc) часто падает или «висит».
# Надёжный путь — unsquashfs по смещению squashfs (магия hsqs).
extract_appimage() {
    img="$1"
    dest="$2"
    parent=$(dirname "$dest")
    rm -rf "$dest" "$parent/squashfs-root"
    set_phase extract
    echo "extract AppImage -> $dest" >>"$LOG"

    is_musl=0
    if [ -f /lib/ld-musl-x86_64.so.1 ] || [ -f /lib/ld-musl-aarch64.so.1 ]; then
        is_musl=1
        echo "musl detected — unsquashfs first" >>"$LOG"
    fi

    if [ "$is_musl" = 0 ]; then
        if ( cd "$parent" && "$img" --appimage-extract >>"$LOG" 2>&1 ); then
            if [ -d "$parent/squashfs-root" ]; then
                [ "$parent/squashfs-root" = "$dest" ] || mv "$parent/squashfs-root" "$dest"
            fi
            [ -x "$dest/AppRun" ] && return 0
        fi
        echo "runtime --appimage-extract failed, fallback unsquashfs" >>"$LOG"
    fi

    command -v unsquashfs >/dev/null 2>&1 \
        || apk add --no-progress --cache-dir /var/lib/gtos/apk-cache squashfs-tools >>"$LOG" 2>&1 \
        || true
    command -v unsquashfs >/dev/null 2>&1 || return 1

    off=$(find_squashfs_offset "$img" || true)
    [ -n "$off" ] || return 1
    echo "unsquashfs -o $off (validated squashfs v4)" >>"$LOG"
    unsquashfs -f -o "$off" -d "$dest" "$img" >>"$LOG" 2>&1 || return 1
    # доступно всем сеансам (misha/test2), иначе Permission denied у su-exec
    chmod -R a+rX "$dest" 2>/dev/null || true
    chmod 755 "$dest" 2>/dev/null || true
    # строго: без AppRun установка бесполезна (раньше хватало «просто каталог»)
    if [ -e "$dest/AppRun" ] || [ -L "$dest/AppRun" ]; then
        chmod 755 "$dest/AppRun" 2>/dev/null || true
        return 0
    fi
    apprun=$(find "$dest" -maxdepth 3 \( -type f -o -type l \) -name AppRun 2>/dev/null | head -n 1 || true)
    if [ -n "$apprun" ]; then
        chmod 755 "$apprun" 2>/dev/null || true
        return 0
    fi
    echo "ERROR: после unsquashfs нет AppRun в $dest" >>"$LOG"
    ls -la "$dest" >>"$LOG" 2>&1 || true
    return 1
}

# Electron под proot иногда видит /proc/self/exe как usr/bin/<app> (symlink) —
# кладём ресурсы рядом, чтобы V8 snapshot и resources/app находились в любом случае.
link_electron_assets() {
    sq="$1"
    for link in "$sq"/usr/bin/*; do
        [ -L "$link" ] || continue
        real=$(readlink -f "$link" 2>/dev/null || true)
        [ -n "$real" ] && [ -f "$real" ] || continue
        rdir=$(dirname "$real")
        [ -f "$rdir/v8_context_snapshot.bin" ] || [ -f "$rdir/snapshot_blob.bin" ] || continue
        bdir=$(dirname "$link")
        [ "$rdir" = "$bdir" ] && continue
        for a in v8_context_snapshot.bin snapshot_blob.bin icudtl.dat resources.pak \
            chrome_100_percent.pak chrome_200_percent.pak locales resources \
            libffmpeg.so libEGL.so libGLESv2.so libvk_swiftshader.so libvulkan.so.1 vk_swiftshader_icd.json; do
            [ -e "$rdir/$a" ] || continue
            [ -e "$bdir/$a" ] || ln -s "$rdir/$a" "$bdir/$a" 2>/dev/null || true
        done
        echo "electron assets linked: $bdir -> $rdir" >>"$LOG"
    done
}

write_appimage_launcher() {
    root_dir="$1"
    apprun="$2"
    dir=$(dirname "$apprun")
    base=$(basename "$apprun")
    # На musl — через gtos-glibc-run (proot + Ubuntu base + Electron flags). На glibc — напрямую.
    body=$(cat <<EOF
export DISPLAY="\${DISPLAY:-:0}"
export APPDIR="$root_dir"
export LIBGL_ALWAYS_SOFTWARE="\${LIBGL_ALWAYS_SOFTWARE:-1}"
export ELECTRON_DISABLE_GPU="\${ELECTRON_DISABLE_GPU:-1}"
echo "GTOS launch: appdir=$root_dir" >&2
if [ ! -d "$root_dir" ]; then
  echo "GTOS: нет $root_dir — переустановите из Магазина" >&2
  exit 1
fi
if [ -x /usr/bin/gtos-glibc-run ]; then
  exec /usr/bin/gtos-glibc-run "$root_dir" "\$@"
fi
cd "$dir" || exit 1
exec ./$base --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox "\$@"
EOF
)
    write_launcher "$body"
}

install_alpine() {
    pkg=$(printf '%s' "$APK" | tr -cd 'A-Za-z0-9._+-')
    [ -n "$pkg" ] || fail 3 "нет имени apk"
    printf '%s\n' \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/main" \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/community" \
        >/etc/apk/repositories
    echo "apk add $pkg (branch=$BRANCH)" >>"$LOG"
    kill_prep_hb 2>/dev/null || true
    # heartbeat: имитируем прогресс 8→85%, чтобы UI не замирал на 8%
    set_phase apk
    (
        n=0
        while [ "$n" -lt 900 ]; do
            # ~1 МБ/тик — формула UI 8 + bytes/(256KiB) растёт заметно
            echo "$((n * 256 * 1024))" >/tmp/gtos-store-bytes
            echo apk >/tmp/gtos-store-phase
            echo "Установка «$pkg»… ${n}с" >/tmp/gtos-store-label
            n=$((n + 1))
            sleep 1
        done
    ) &
    hb_pid=$!
    finish_hb() { kill "$hb_pid" 2>/dev/null || true; wait "$hb_pid" 2>/dev/null || true; }

    # уже стоит
    if command -v "${BIN:-$pkg}" >/dev/null 2>&1 || apk info -e "$pkg" >/dev/null 2>&1; then
        echo "package already present: $pkg" >>"$LOG"
        finish_hb
        bin="${BIN:-$pkg}"
        write_launcher "export DISPLAY=\${DISPLAY:-:0}; exec $(command -v "$bin" 2>/dev/null || echo "$bin") \"\$@\""
        ok_done
    fi

    try=1
    while [ "$try" -le 3 ]; do
        echo "apk update try $try" >>"$LOG"
        if timeout 60 apk update --no-progress --cache-dir /var/lib/gtos/apk-cache >>"$LOG" 2>&1; then
            break
        fi
        try=$((try + 1))
        sleep 2
    done

    try=1
    while [ "$try" -le 3 ]; do
        echo "apk add $pkg try $try" >>"$LOG"
        if timeout 300 apk add --no-progress --cache-dir /var/lib/gtos/apk-cache "$pkg" >>"$LOG" 2>&1; then
            finish_hb
            bin="${BIN:-$pkg}"
            write_launcher "export DISPLAY=\${DISPLAY:-:0}; exec $(command -v "$bin" 2>/dev/null || echo "$bin") \"\$@\""
            ok_done
        fi
        try=$((try + 1))
        sleep 2
    done

    # запас: .apk по URL + зависимости из индекса
    case "$URL" in
        *.apk*)
            echo "fallback: download apk from URL" >>"$LOG"
            apk_file="$ROOT/dl/pkg.apk"
            mkdir -p "$ROOT/dl"
            if download "$apk_file" 50000; then
                if timeout 300 apk add --no-progress --allow-untrusted --cache-dir /var/lib/gtos/apk-cache "$apk_file" >>"$LOG" 2>&1 \
                    || timeout 300 apk add --no-progress --allow-untrusted --cache-dir /var/lib/gtos/apk-cache --force-non-repository "$apk_file" >>"$LOG" 2>&1; then
                    finish_hb
                    bin="${BIN:-$pkg}"
                    write_launcher "export DISPLAY=\${DISPLAY:-:0}; exec $(command -v "$bin" 2>/dev/null || echo "$bin") \"\$@\""
                    ok_done
                fi
            fi
            ;;
    esac

    finish_hb
    if command -v "${BIN:-$pkg}" >/dev/null 2>&1 || apk info -e "$pkg" >/dev/null 2>&1; then
        bin="${BIN:-$pkg}"
        write_launcher "export DISPLAY=\${DISPLAY:-:0}; exec $(command -v "$bin" 2>/dev/null || echo "$bin") \"\$@\""
        ok_done
    fi
    if ! apk search -q "$pkg" 2>/dev/null | head -n 1 | grep -q .; then
        fail 1 "пакета «$pkg» нет в репозитории $BRANCH — проверьте сеть"
    fi
    fail 1 "не удалось установить «$pkg» — нет сети или не хватило места"
}

install_linux_appimage() {
    img="$ROOT/dl/app.AppImage"
    download "$img" || fail 1 "не удалось скачать AppImage (сеть/URL/403)"
    chmod 755 "$img"
    extract_appimage "$img" "$ROOT/squashfs-root" || fail 1 "не удалось распаковать AppImage"
    apprun="$ROOT/squashfs-root/AppRun"
    if [ ! -e "$apprun" ]; then
        apprun=$(find "$ROOT/squashfs-root" -type f -name AppRun 2>/dev/null | head -n 1 || true)
    fi
    [ -n "$apprun" ] && [ -e "$apprun" ] || fail 1 "нет AppRun в AppImage"
    chmod 755 "$apprun" 2>/dev/null || true
    chmod -R a+rX "$ROOT/squashfs-root" "$ROOT/bin" "$ROOT" 2>/dev/null || true
    link_electron_assets "$ROOT/squashfs-root"
    write_appimage_launcher "$ROOT/squashfs-root" "$apprun"
    ok_done
}

install_linux_deb() {
    deb="$ROOT/dl/pkg.deb"
    download "$deb" || fail 1 "не удалось скачать .deb"
    command -v ar >/dev/null 2>&1 || apk add --no-progress binutils >>"$LOG" 2>&1 || true
    rm -rf "$ROOT/root" "$ROOT/dl/extract"
    mkdir -p "$ROOT/root" "$ROOT/dl/extract"
    if ! (
        cd "$ROOT/dl/extract"
        ar x "$deb" >>"$LOG" 2>&1 || exit 1
        data=$(ls data.tar.* 2>/dev/null | head -n 1)
        [ -n "$data" ] || exit 1
        tar -xf "$data" -C "$ROOT/root" >>"$LOG" 2>&1 || exit 1
    ); then
        fail 1 "не удалось распаковать .deb"
    fi
    target=""
    if [ -n "$BIN" ] && [ -x "$ROOT/root/usr/bin/$BIN" ]; then
        target="$ROOT/root/usr/bin/$BIN"
    elif [ -n "$BIN" ] && [ -x "$ROOT/root/bin/$BIN" ]; then
        target="$ROOT/root/bin/$BIN"
    else
        target=$(find "$ROOT/root/usr/bin" "$ROOT/root/bin" -type f -executable 2>/dev/null | head -n 1 || true)
    fi
    [ -n "$target" ] || fail 1 "не найден исполняемый файл в .deb"
    write_launcher "export PATH=\"$ROOT/root/usr/bin:$ROOT/root/bin:\$PATH\"; export LD_LIBRARY_PATH=\"$ROOT/root/usr/lib:$ROOT/root/lib:\${LD_LIBRARY_PATH:-}\"; exec \"$target\" \"\$@\""
    ok_done
}

install_linux_tar() {
    archive="$ROOT/dl/pkg.tgz"
    download "$archive" || fail 1 "не удалось скачать архив"
    rm -rf "$ROOT/root"
    mkdir -p "$ROOT/root"
    tar -xaf "$archive" -C "$ROOT/root" >>"$LOG" 2>&1 || fail 1 "не удалось распаковать архив"
    target=""
    if [ -n "$BIN" ]; then
        target=$(find "$ROOT/root" -type f -name "$BIN" 2>/dev/null | head -n 1 || true)
    fi
    [ -n "$target" ] || target=$(find "$ROOT/root" -type f -executable 2>/dev/null | head -n 1 || true)
    [ -n "$target" ] || fail 1 "не найден бинарник в архиве"
    write_launcher "exec \"$target\" \"\$@\""
    ok_done
}

install_windows() {
    ensure_wine || fail 1 "не удалось установить Wine (нужен для Windows-приложений)"
    export WINEPREFIX="$ROOT/wine"
    export WINEDEBUG="-all"
    mkdir -p "$WINEPREFIX"
    wineboot -i >>"$LOG" 2>&1 || true

    case "$FORMAT" in
        zip)
            z="$ROOT/dl/app.zip"
            download "$z" || fail 1 "не удалось скачать zip"
            command -v unzip >/dev/null 2>&1 || apk add --no-progress unzip >>"$LOG" 2>&1 || true
            rm -rf "$ROOT/win"
            mkdir -p "$ROOT/win"
            unzip -o "$z" -d "$ROOT/win" >>"$LOG" 2>&1 || fail 1 "unzip не удался"
            exe_path=""
            if [ -n "$EXE" ]; then
                exe_path=$(find "$ROOT/win" -type f -iname "$EXE" 2>/dev/null | head -n 1 || true)
            fi
            [ -n "$exe_path" ] || exe_path=$(find "$ROOT/win" -type f -iname '*.exe' 2>/dev/null | head -n 1 || true)
            [ -n "$exe_path" ] || fail 1 "в архиве нет .exe"
            write_launcher "export WINEPREFIX=\"$ROOT/wine\"; export WINEDEBUG=-all; export DISPLAY=\${DISPLAY:-:0}; exec wine \"$exe_path\" \"\$@\""
            ok_done
            ;;
        msi)
            m="$ROOT/dl/setup.msi"
            download "$m" || fail 1 "не удалось скачать msi"
            wine msiexec /i "$m" /qn >>"$LOG" 2>&1 || wine msiexec /i "$m" >>"$LOG" 2>&1 || fail 1 "msiexec не удался"
            write_launcher "export WINEPREFIX=\"$ROOT/wine\"; export WINEDEBUG=-all; export DISPLAY=\${DISPLAY:-:0}; exec wine explorer \"\$@\""
            ok_done
            ;;
        exe|*)
            e="$ROOT/dl/setup.exe"
            download "$e" || fail 1 "не удалось скачать exe"
            # portable: просто запускаем; installer — тихая попытка
            if [ "${PORTABLE:-0}" = "1" ] || [ "$FORMAT" = "portable" ]; then
                cp -f "$e" "$ROOT/app.exe"
                write_launcher "export WINEPREFIX=\"$ROOT/wine\"; export WINEDEBUG=-all; export DISPLAY=\${DISPLAY:-:0}; exec wine \"$ROOT/app.exe\" \"\$@\""
                ok_done
            fi
            wine "$e" /S /silent /VERYSILENT /NORESTART >>"$LOG" 2>&1 \
                || wine "$e" >>"$LOG" 2>&1 \
                || true
            # если это portable-like — копируем как app.exe
            cp -f "$e" "$ROOT/app.exe"
            write_launcher "export WINEPREFIX=\"$ROOT/wine\"; export WINEDEBUG=-all; export DISPLAY=\${DISPLAY:-:0}; exec wine \"$ROOT/app.exe\" \"\$@\""
            ok_done
            ;;
    esac
}

echo "job id=$ID source=$SOURCE format=$FORMAT apk=$APK" >>"$LOG"

# Ремонт битого extract (ложный hsqs → нет AppRun): только unsquashfs из кэша
if [ -n "$REPAIR_ID" ]; then
    img="$ROOT/dl/app.AppImage"
    [ -f "$img" ] || fail 1 "нет кэша AppImage ($img) — переустановите из Магазина"
    echo "GTOS_REPAIR_APPIMAGE $ID" >>"$LOG"
    set_phase extract
    # снести битый/закрытый каталог (Permission denied у пользователей)
    rm -rf "$ROOT/squashfs-root"
    extract_appimage "$img" "$ROOT/squashfs-root" || fail 1 "не удалось перепаковать AppImage"
    apprun="$ROOT/squashfs-root/AppRun"
    if [ ! -e "$apprun" ] && [ ! -L "$apprun" ]; then
        apprun=$(find "$ROOT/squashfs-root" -maxdepth 4 \( -type f -o -type l \) -name AppRun 2>/dev/null | head -n 1 || true)
    fi
    [ -n "$apprun" ] && { [ -e "$apprun" ] || [ -L "$apprun" ]; } || fail 1 "после ремонта всё ещё нет AppRun"
    chmod 755 "$apprun" 2>/dev/null || true
    chmod -R a+rX "$ROOT/squashfs-root" "$ROOT/bin" 2>/dev/null || true
    chmod 755 "$ROOT" "$ROOT/bin" 2>/dev/null || true
    link_electron_assets "$ROOT/squashfs-root"
    write_appimage_launcher "$ROOT/squashfs-root" "$apprun"
    echo "GTOS_REPAIR_OK $ID" >>"$LOG"
    { echo "GTOS_REPAIR_OK $ID" >/dev/ttyS0; } 2>/dev/null || true
    ok_done
fi

case "$SOURCE" in
    web)
        write_launcher "echo 'web app'; exit 0"
        ok_done
        ;;
    linux)
        case "$FORMAT" in
            appimage|AppImage) install_linux_appimage ;;
            deb) install_linux_deb ;;
            tar|tgz|tar.gz|txz) install_linux_tar ;;
            *) fail 3 "неизвестный linux format: $FORMAT" ;;
        esac
        ;;
    windows|win)
        install_windows
        ;;
    alpine|*)
        install_alpine
        ;;
esac
