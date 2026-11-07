#!/bin/sh
# GT/OS Store installer: alpine | linux (AppImage/deb/tar) | windows (Wine)
set -eu

JOB="${1:-/tmp/gtos-store-job.env}"
LOG="${GTOS_STORE_LOG:-/tmp/gtos-apk-log}"
RC_FILE="${GTOS_STORE_RC:-/tmp/gtos-store-rc}"
DONE_FILE="${GTOS_STORE_DONE:-/tmp/gtos-store-done}"
URL_FILE="${GTOS_STORE_URL:-/tmp/gtos-store-url.txt}"

rm -f "$DONE_FILE" "$RC_FILE"
: >"$LOG"
echo "GTOS_STORE_INSTALL start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LOG"

fail() {
    code="${1:-1}"
    msg="${2:-install failed}"
    echo "ERROR: $msg" >>"$LOG"
    echo "$code" >"$RC_FILE"
    # совместимость со старым таймером оболочки
    echo "$code" >/tmp/gtos-apk-rc
    echo done >"$DONE_FILE"
    echo done >/tmp/gtos-apk-done
    exit 0
}

ok_done() {
    echo 0 >"$RC_FILE"
    echo 0 >/tmp/gtos-apk-rc
    echo done >"$DONE_FILE"
    echo done >/tmp/gtos-apk-done
    echo "GTOS_STORE_INSTALL ok" >>"$LOG"
    exit 0
}

[ -f "$JOB" ] || fail 2 "нет файла задания $JOB"

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
URL=""
if [ -f "$URL_FILE" ]; then
    URL=$(tr -d '\r' <"$URL_FILE" | head -n 1)
fi
URL="${URL:-${APP_URL:-}}"

[ -n "$ID" ] || fail 2 "пустой ID"

ROOT="/var/lib/gtos/apps/$ID"
mkdir -p "$ROOT/bin" "$ROOT/dl" /var/lib/gtos/apk-cache /etc/apk
USER_NAME="${GTOS_USER:-misha}"

write_launcher() {
    body="$1"
    printf '%s\n' "#!/bin/sh" "$body" >"$ROOT/bin/launch"
    chmod 755 "$ROOT/bin/launch"
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

download() {
    dest="$1"
    [ -n "$URL" ] || return 1
    echo "download $URL -> $dest" >>"$LOG"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 2 --connect-timeout 20 --max-time 900 -o "$dest" "$URL" >>"$LOG" 2>&1
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$dest" "$URL" >>"$LOG" 2>&1
    else
        return 1
    fi
}

install_alpine() {
    pkg=$(printf '%s' "$APK" | tr -cd 'A-Za-z0-9._+-')
    [ -n "$pkg" ] || fail 3 "нет имени apk"
    printf '%s\n' \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/main" \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/community" \
        >/etc/apk/repositories
    echo "apk add $pkg" >>"$LOG"
    apk update --cache-dir /var/lib/gtos/apk-cache >>"$LOG" 2>&1 || true
    if apk add --cache-dir /var/lib/gtos/apk-cache "$pkg" >>"$LOG" 2>&1; then
        bin="${BIN:-$pkg}"
        write_launcher "exec $(command -v "$bin" 2>/dev/null || echo "$bin") \"\$@\""
        ok_done
    fi
    fail 1 "apk add $pkg не удалось"
}

install_linux_appimage() {
    img="$ROOT/dl/app.AppImage"
    download "$img" || fail 1 "не удалось скачать AppImage"
    chmod 755 "$img"
    rm -rf "$ROOT/squashfs-root"
    # без FUSE — извлекаем (не вызывать fail внутри subshell: он делает exit 0)
    if ! ( cd "$ROOT" && "$img" --appimage-extract >>"$LOG" 2>&1 ); then
        fail 1 "не удалось распаковать AppImage"
    fi
    [ -x "$ROOT/squashfs-root/AppRun" ] || fail 1 "нет AppRun в AppImage"
    write_launcher "cd \"$ROOT/squashfs-root\" || exit 1; exec ./AppRun \"\$@\""
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
