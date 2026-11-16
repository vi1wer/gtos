#!/bin/sh
# Запуск glibc AppImage/Electron на musl GT/OS через proot + Ubuntu base.
# Usage:
#   gtos-glibc-run --setup              # только root: proot + rootfs + GUI libs
#   gtos-glibc-run <appdir> [args...]
#   gtos-glibc-run --exec <binary> [args...]
set -eu

ROOT="${GTOS_GLIBC_ROOT:-/var/lib/gtos/glibc-root}"
MARKER="$ROOT/.gtos-ok"
ELECTRON_OK="$ROOT/.gtos-electron-ok"
ROOT_VERSION=4
UBUNTU_URL="${GTOS_GLIBC_ROOTFS_URL:-https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/ubuntu-base-22.04.5-base-amd64.tar.gz}"
# лог всегда в /tmp — apk/root писали в /var и ловили Permission denied от пользователя
LOG="${GTOS_GLIBC_LOG:-/tmp/gtos-glibc-run-$(id -u).log}"

log() {
    echo "$*" >>"$LOG" 2>/dev/null || true
    echo "$*" >&2
    { echo "GTOS_GLIBC $*" >/dev/ttyS0; } 2>/dev/null || true
}

need_root() {
    if [ "$(id -u)" != "0" ]; then
        log "GTOS glibc: нужно root для setup (сейчас uid=$(id -u))"
        return 1
    fi
    return 0
}

# В образе лежит статический /usr/bin/proot (из proot-static) — apk не нужен.
ensure_proot() {
    if [ -x /usr/bin/proot ]; then
        return 0
    fi
    if [ -x /usr/bin/proot.static ]; then
        ln -sf /usr/bin/proot.static /usr/bin/proot 2>/dev/null || cp -f /usr/bin/proot.static /usr/bin/proot
        [ -x /usr/bin/proot ] && return 0
    fi
    if command -v proot >/dev/null 2>&1; then
        return 0
    fi
    log "GTOS glibc: нет /usr/bin/proot в образе — обновите ISO/initrd (refresh_ui)"
    return 1
}

PREBUILT=""
for pre in /usr/share/gtos/gtos-glibc-root.tar.gz /run/initramfs/usr/share/gtos/gtos-glibc-root.tar.gz; do
    if [ -f "$pre" ] && [ "$(stat -c%s "$pre" 2>/dev/null || echo 0)" -gt 5000000 ]; then
        PREBUILT=$pre
        break
    fi
done

root_valid() {
    [ -f "$MARKER" ] && [ -f "$ELECTRON_OK" ] || return 1
    [ -e "$ROOT/usr/lib/x86_64-linux-gnu/libX11.so.6" ] || return 1
    [ -e "$ROOT/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" ] || return 1
    [ -L "$ROOT/lib64/ld-linux-x86-64.so.2" ] || [ -e "$ROOT/lib64/ld-linux-x86-64.so.2" ] || return 1
    [ -x "$ROOT/bin/sh" ] || return 1
    if [ -n "$PREBUILT" ]; then
        [ "$(cat "$ROOT/.gtos-root-version" 2>/dev/null)" = "$ROOT_VERSION" ] || return 1
    fi
    return 0
}

ensure_rootfs() {
    if root_valid; then
        return 0
    fi
    need_root || return 1
    mkdir -p /var/lib/gtos /tmp

    # 0) готовый root с GUI libs (собрано на хосте) — секунды, без dpkg
    if [ -n "$PREBUILT" ]; then
        log "GTOS glibc: распаковка готового root v$ROOT_VERSION ($PREBUILT)…"
        rm -rf "$ROOT"
        mkdir -p "$ROOT"
        if tar -xzf "$PREBUILT" -C "$ROOT" >>"$LOG" 2>&1; then
            mkdir -p "$ROOT/home" "$ROOT/tmp" "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" "$ROOT/opt" "$ROOT/run"
            chmod 1777 "$ROOT/tmp" 2>/dev/null || true
            if [ -f /etc/resolv.conf ]; then
                cp -f /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || true
            fi
            ensure_proot && proot -r "$ROOT" /sbin/ldconfig >>"$LOG" 2>&1 || log "GTOS glibc: ldconfig warn"
            chmod -R a+rX "$ROOT" 2>/dev/null || true
            touch "$MARKER" "$ELECTRON_OK"
            chmod 644 "$MARKER" "$ELECTRON_OK" 2>/dev/null || true
            if root_valid; then
                log "GTOS glibc: готовый root OK"
                return 0
            fi
            log "GTOS glibc: готовый root неполный: $(ls -la "$ROOT/lib64/" 2>&1 | tail -n 3 | tr '\n' ' ')"
            return 1
        fi
        log "GTOS glibc: готовый root не распаковался — fallback"
    fi

    tmp=/var/lib/gtos/ubuntu-base.tar.gz
    # 1) локальная копия из образа (без сети)
    for cand in \
        /usr/share/gtos/ubuntu-base.tar.gz \
        /usr/share/gtos/ubuntu-base-22.04.5-base-amd64.tar.gz \
        /run/initramfs/usr/share/gtos/ubuntu-base.tar.gz
    do
        if [ -f "$cand" ]; then
            sz=$(stat -c%s "$cand" 2>/dev/null || echo 0)
            if [ "$sz" -gt 1000000 ]; then
                log "GTOS glibc: беру ubuntu-base из образа ($cand)"
                cp -f "$cand" "$tmp" || return 1
                break
            fi
        fi
    done
    if [ ! -f "$tmp" ] || [ "$(stat -c%s "$tmp" 2>/dev/null || echo 0)" -lt 1000000 ]; then
        log "GTOS glibc: скачиваю Ubuntu base rootfs…"
        if command -v curl >/dev/null 2>&1; then
            curl -fL -A "Mozilla/5.0 GTOS-glibc/1.6" --retry 3 --retry-delay 2 \
                --connect-timeout 30 --max-time 1800 -o "$tmp" "$UBUNTU_URL" >>"$LOG" 2>&1 \
                || return 1
        elif command -v wget >/dev/null 2>&1; then
            wget -O "$tmp" "$UBUNTU_URL" >>"$LOG" 2>&1 || return 1
        else
            log "GTOS glibc: нет curl/wget и нет локального ubuntu-base"
            return 1
        fi
    fi
    sz=$(stat -c%s "$tmp" 2>/dev/null || echo 0)
    if [ "$sz" -lt 1000000 ]; then
        log "GTOS glibc: архив слишком маленький ($sz)"
        return 1
    fi
    log "GTOS glibc: распаковка rootfs…"
    rm -rf "$ROOT"
    mkdir -p "$ROOT"
    tar -xzf "$tmp" -C "$ROOT" >>"$LOG" 2>&1 || return 1
    mkdir -p "$ROOT/home" "$ROOT/tmp" "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" "$ROOT/opt" "$ROOT/run"
    if [ -f /etc/resolv.conf ]; then
        cp -f /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || true
    else
        printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' >"$ROOT/etc/resolv.conf"
    fi
    if ! grep -q '^misha:' "$ROOT/etc/passwd" 2>/dev/null; then
        echo 'misha:x:1000:1000:Misha:/home/misha:/bin/bash' >>"$ROOT/etc/passwd"
    fi
    if ! grep -q '^misha:' "$ROOT/etc/group" 2>/dev/null; then
        echo 'misha:x:1000:' >>"$ROOT/etc/group"
    fi
    # пользователю нужно читать rootfs
    chmod -R a+rX "$ROOT" 2>/dev/null || true
    touch "$MARKER"
    chmod 644 "$MARKER" 2>/dev/null || true
    rm -f "$ELECTRON_OK"
    log "GTOS glibc: rootfs готов ($ROOT)"
    return 0
}

# ubuntu-base без GUI — Cursor/Electron падают на libX11/libnss. Докидываем пакеты.
ensure_electron_deps() {
    if [ -f "$ELECTRON_OK" ] && ls "$ROOT/usr/lib/x86_64-linux-gnu"/libX11.so* >/dev/null 2>&1 \
        && ls "$ROOT/usr/lib/x86_64-linux-gnu"/libnss3.so* >/dev/null 2>&1; then
        return 0
    fi
    need_root || return 1
    ensure_proot || return 1
    [ -f "$MARKER" ] || return 1
    mkdir -p /tmp /dev/shm
    chmod 1777 /tmp /dev/shm 2>/dev/null || true
    if [ -f /etc/resolv.conf ]; then
        cp -f /etc/resolv.conf "$ROOT/etc/resolv.conf" 2>/dev/null || true
    fi

    log "GTOS glibc: ставлю GUI/Electron libs (apt, сеть)…"
    # shellcheck disable=SC2016
    if ! proot --kill-on-exit \
        -r "$ROOT" \
        -b /dev \
        -b /proc \
        -b /sys \
        -b /tmp:/tmp \
        -b /etc/resolv.conf:/etc/resolv.conf \
        /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        /bin/bash -c '
set -e
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates \
  libnss3 libnspr4 \
  libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libdbus-1-3 \
  libxcb1 libxkbcommon0 \
  libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
  libgbm1 libpango-1.0-0 libcairo2 \
  libasound2 libgtk-3-0 libxshmfence1 libglib2.0-0 \
  libgdk-pixbuf-2.0-0 libpangocairo-1.0-0 \
  fonts-dejavu-core fontconfig \
  >/dev/null
rm -rf /var/lib/apt/lists/*
' >>"$LOG" 2>&1; then
        log "GTOS glibc: apt install electron deps failed — см. $LOG"
        return 1
    fi
    touch "$ELECTRON_OK"
    chmod 644 "$ELECTRON_OK" 2>/dev/null || true
    chmod -R a+rX "$ROOT" 2>/dev/null || true
    log "GTOS glibc: electron deps OK"
    return 0
}

do_setup() {
    : >"$LOG"
    LOCK=/tmp/gtos-glibc-setup.lock
    if ! mkdir "$LOCK" 2>/dev/null; then
        log "GTOS glibc: setup уже идёт — жду"
        n=0
        while [ -d "$LOCK" ] && [ "$n" -lt 600 ]; do
            sleep 1
            n=$((n + 1))
        done
        root_valid && { log "GTOS glibc: setup OK (параллельный)"; return 0; }
        mkdir "$LOCK" 2>/dev/null || true
    fi
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
    rc=0
    ensure_proot || rc=1
    [ "$rc" = 0 ] && { ensure_rootfs || rc=1; }
    [ "$rc" = 0 ] && { ensure_electron_deps || rc=1; }
    [ "$rc" = 0 ] && log "GTOS glibc: setup OK"
    return "$rc"
}

if [ "${1:-}" = "--setup" ]; then
    do_setup
    exit $?
fi

# Уже на glibc-хосте — без proot
if [ ! -f /lib/ld-musl-x86_64.so.1 ] && [ ! -f /lib/ld-musl-aarch64.so.1 ]; then
    if [ "${1:-}" = "--exec" ]; then
        shift
        exec "$@"
    fi
    appdir=${1:-}
    [ -n "$appdir" ] || { echo "usage: gtos-glibc-run <appdir> [args...]" >&2; exit 2; }
    shift
    cd "$appdir" || exit 1
    if [ -x ./AppRun ]; then
        exec ./AppRun --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox "$@"
    fi
    exec "$@"
fi

# musl: setup должен быть сделан от root заранее; здесь только запуск
if ! command -v proot >/dev/null 2>&1; then
    log "GTOS glibc: proot не найден — нужен root: gtos-glibc-run --setup"
    exit 1
fi
if ! root_valid; then
    log "GTOS glibc: rootfs не готов/устарел — нужен root: gtos-glibc-run --setup"
    exit 1
fi

export DISPLAY="${DISPLAY:-:0}"
export HOME="${HOME:-/home/misha}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export ELECTRON_DISABLE_GPU="${ELECTRON_DISABLE_GPU:-1}"
export ELECTRON_OZONE_PLATFORM_HINT="${ELECTRON_OZONE_PLATFORM_HINT:-x11}"

BIN_MODE=0
if [ "${1:-}" = "--exec" ]; then
    BIN_MODE=1
    shift
fi

if [ "$BIN_MODE" = 1 ]; then
    target=$1
    shift
    appdir=$(dirname "$target")
else
    appdir=${1:-}
    [ -n "$appdir" ] || { echo "usage: gtos-glibc-run <appdir> [args...]" >&2; exit 2; }
    shift
    if [ -e "$appdir/AppRun" ] || [ -L "$appdir/AppRun" ]; then
        target="$appdir/AppRun"
    else
        target=$(find "$appdir" -maxdepth 4 \( -type f -o -type l \) -name AppRun 2>/dev/null | head -n 1 || true)
    fi
    # Cursor/VS Code: иногда только бинарник без AppRun (битый extract)
    if [ -z "$target" ]; then
        for cand in "$appdir/cursor" "$appdir/code" "$appdir/usr/bin/cursor" "$appdir/usr/share/cursor/cursor" \
            "$appdir/usr/lib/cursor/cursor" "$appdir/usr/share/cursor/cursor"; do
            if [ -e "$cand" ]; then
                target=$cand
                break
            fi
        done
    fi
    if [ -z "$target" ]; then
        target=$(find "$appdir" -maxdepth 5 -type f \( -name cursor -o -name code -o -name Obsidian \) 2>/dev/null | head -n 1 || true)
    fi
    if [ -z "$target" ]; then
        log "GTOS glibc: нет AppRun в $appdir"
        # диагностика только в лог/serial — не в stdout (тост пользователя)
        { ls -la "$appdir" 2>&1 | head -n 8 | sed 's/^/GTOS_APPRUN_LS /' >/dev/ttyS0; } 2>/dev/null || true
        exit 1
    fi
    # Electron под proot: /proc/self/exe указывает на путь symlink (usr/bin/cursor),
    # и V8 ищет v8_context_snapshot.bin не в том каталоге. Запускаем настоящий бинарник.
    desk=$(ls "$appdir"/*.desktop 2>/dev/null | head -n 1 || true)
    if [ -n "$desk" ]; then
        exe=$(grep -m1 '^Exec=' "$desk" | cut -d= -f2- | awk '{print $1}')
        case "$exe" in
            /*) cand="$appdir$exe" ;;
            *) cand="$appdir/usr/bin/$exe" ;;
        esac
        if [ -n "$exe" ] && [ -e "$cand" ]; then
            real=$(readlink -f "$cand" 2>/dev/null || true)
            if [ -n "$real" ] && [ -f "$real" ] && [ -f "$(dirname "$real")/v8_context_snapshot.bin" -o -f "$(dirname "$real")/snapshot_blob.bin" ]; then
                log "GTOS glibc: Electron напрямую: $real"
                target=$real
                export LD_LIBRARY_PATH="$appdir/usr/lib:${LD_LIBRARY_PATH:-}"
            fi
        fi
    fi
fi

# Electron/Chromium
IS_ELECTRON=0
if [ -e "$appdir/chrome-sandbox" ] || [ -e "$appdir/cursor" ] || [ -e "$appdir/code" ] \
    || [ -e "$appdir/obsidian" ] || [ -d "$appdir/resources/app" ] \
    || [ -f "$(dirname "$target")/v8_context_snapshot.bin" ] \
    || echo "$appdir$target" | grep -qiE 'cursor|electron|codium|obsidian|bitwarden|joplin'; then
    IS_ELECTRON=1
fi

EXTRA=""
if [ "$IS_ELECTRON" = 1 ]; then
    EXTRA="--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox --no-zygote --ozone-platform=x11 --disable-features=VizDisplayCompositor"
fi

mkdir -p /tmp /dev/shm
chmod 1777 /tmp /dev/shm 2>/dev/null || true

RUNLOG=/tmp/gtos-glibc-app-$(id -u).log
: >"$RUNLOG" 2>/dev/null || true
rc=0
( sleep 40; log "GTOS glibc: +40s: $(tail -n 8 "$RUNLOG" 2>/dev/null | tr '\n' '|' | cut -c1-700)" ) &

# Electron: proot ломает mmap(V8 snapshot). Запуск через glibc ld.so напрямую на musl-хосте.
if [ "$IS_ELECTRON" = 1 ]; then
    LD=""
    for cand in \
        "$ROOT/lib64/ld-linux-x86-64.so.2" \
        "$ROOT/usr/lib64/ld-linux-x86-64.so.2" \
        "$ROOT/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2" \
        "$ROOT/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
    do
        if [ -x "$cand" ] || [ -e "$cand" ]; then
            LD=$cand
            break
        fi
    done
    if [ -n "$LD" ]; then
        edir=$(dirname "$target")
        # страховка: fuse browser_v8_context_snapshot
        if [ -f "$edir/v8_context_snapshot.bin" ] && [ ! -f "$edir/browser_v8_context_snapshot.bin" ]; then
            ln -sf v8_context_snapshot.bin "$edir/browser_v8_context_snapshot.bin" 2>/dev/null || \
                cp -f "$edir/v8_context_snapshot.bin" "$edir/browser_v8_context_snapshot.bin" 2>/dev/null || true
        fi
        sz=$(stat -c%s "$edir/v8_context_snapshot.bin" 2>/dev/null || echo 0)
        if [ "$sz" -lt 100000 ]; then
            log "GTOS glibc: битый/пустой v8_context_snapshot.bin ($sz) — нужен repair"
            exit 1
        fi
        LIBPATH="$edir"
        LIBPATH="$LIBPATH:$ROOT/usr/lib/x86_64-linux-gnu"
        LIBPATH="$LIBPATH:$ROOT/lib/x86_64-linux-gnu"
        LIBPATH="$LIBPATH:$ROOT/usr/lib64:$ROOT/lib64"
        LIBPATH="$LIBPATH:$ROOT/usr/lib:$ROOT/lib"
        LIBPATH="$LIBPATH:${LD_LIBRARY_PATH:-}"
        log "GTOS glibc: ld.so run $target (no proot, DISPLAY=$DISPLAY uid=$(id -u) snap=$sz)"
        cd "$edir" || true
        # shellcheck disable=SC2086
        env -i \
            PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
            HOME="$HOME" \
            USER="${USER:-misha}" \
            LOGNAME="${LOGNAME:-misha}" \
            DISPLAY="$DISPLAY" \
            XAUTHORITY="${XAUTHORITY:-}" \
            XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}" \
            TMPDIR="${TMPDIR:-/tmp}" \
            LIBGL_ALWAYS_SOFTWARE=1 \
            ELECTRON_DISABLE_GPU=1 \
            ELECTRON_OZONE_PLATFORM_HINT=x11 \
            CHROME_DEVEL_SANDBOX= \
            APPDIR="$appdir" \
            LD_LIBRARY_PATH="$LIBPATH" \
            FONTCONFIG_PATH="$ROOT/etc/fonts" \
            "$LD" --library-path "$LIBPATH" "$target" $EXTRA "$@" 2>&1 | tee -a "$RUNLOG" || rc=$?
        log "GTOS glibc: app exit rc=$rc: $(tail -n 12 "$RUNLOG" 2>/dev/null | tr '\n' '|' | cut -c1-900)"
        exit "$rc"
    fi
    log "GTOS glibc: нет ld-linux — fallback proot (V8 может упасть)"
fi

XARGS=""
if [ -n "${XAUTHORITY:-}" ] && [ -f "$XAUTHORITY" ]; then
    XARGS="-b $XAUTHORITY:$XAUTHORITY"
fi
if [ -d /tmp/.X11-unix ]; then
    XARGS="$XARGS -b /tmp/.X11-unix:/tmp/.X11-unix"
fi

log "GTOS glibc: proot run $target $EXTRA (DISPLAY=$DISPLAY uid=$(id -u))"

# shellcheck disable=SC2086
proot --kill-on-exit \
    -r "$ROOT" \
    -b /dev \
    -b /proc \
    -b /sys \
    -b /tmp:/tmp \
    -b /dev/shm:/dev/shm \
    -b /home:/home \
    -b /etc/resolv.conf:/etc/resolv.conf \
    -b "$appdir:$appdir" \
    $XARGS \
    -w "$(dirname "$target")" \
    /usr/bin/env \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    DISPLAY="$DISPLAY" \
    HOME="$HOME" \
    USER="${USER:-misha}" \
    LOGNAME="${LOGNAME:-misha}" \
    XAUTHORITY="${XAUTHORITY:-}" \
    LIBGL_ALWAYS_SOFTWARE=1 \
    ELECTRON_DISABLE_GPU=1 \
    ELECTRON_OZONE_PLATFORM_HINT=x11 \
    CHROME_DEVEL_SANDBOX= \
    APPDIR="$appdir" \
    "$target" $EXTRA "$@" 2>&1 | tee -a "$RUNLOG" || rc=$?
log "GTOS glibc: app exit rc=$rc: $(tail -n 12 "$RUNLOG" 2>/dev/null | tr '\n' '|' | cut -c1-900)"
exit "$rc"
