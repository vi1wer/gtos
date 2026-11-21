#!/bin/sh
# Запуск Windows PE (.exe/.msi) на GT/OS.
# Wine ставится в /var/lib/gtos/glibc-root (постоянный диск), не в tmpfs overlay.
# Usage:
#   gtos-wine-run --setup | --status | <file.exe> [args...]
set -eu

PREFIX="${WINEPREFIX:-/var/lib/gtos/wine-user}"
LOG="${GTOS_WINE_LOG:-/tmp/gtos-wine-last.log}"
READY=/tmp/gtos-wine-ready
FAIL=/tmp/gtos-wine-fail
GLIBC_ROOT="${GTOS_GLIBC_ROOT:-/var/lib/gtos/glibc-root}"
MARKER="$PREFIX/.gtos-wine-ok"

log() {
    echo "$*" >>"$LOG" 2>/dev/null || true
    echo "$*" >&2
    { echo "GTOS_WINE $*" >/dev/ttyS0; } 2>/dev/null || true
}

host_wine() {
    if command -v wine64 >/dev/null 2>&1; then command -v wine64; return 0; fi
    if command -v wine >/dev/null 2>&1; then command -v wine; return 0; fi
    return 1
}

glibc_has_wine() {
    [ -x "$GLIBC_ROOT/usr/bin/wine64" ] || [ -x "$GLIBC_ROOT/usr/bin/wine" ] \
     || [ -x "$GLIBC_ROOT/usr/bin/wine-stable" ]
}

overlay_free_mb() {
    df -m / 2>/dev/null | awk 'NR==2{print $4; exit}'
}

invoke_glibc_wine() {
    WBIN=""
    for c in wine64 wine wine-stable; do
        if [ -x "$GLIBC_ROOT/usr/bin/$c" ]; then
            WBIN=$c
            break
        fi
    done
    [ -n "$WBIN" ] || return 1
    export DISPLAY="${DISPLAY:-:0}"
    export WINEPREFIX="$PREFIX"
    export WINEDEBUG=-all
    mkdir -p "$PREFIX" /tmp
    command -v proot >/dev/null 2>&1 || return 1
    [ -d "$GLIBC_ROOT" ] || return 1
    proot --kill-on-exit \
        -r "$GLIBC_ROOT" \
        -b /dev -b /proc -b /sys -b /tmp:/tmp \
        -b /dev/shm:/dev/shm \
        -b "$PREFIX:$PREFIX" \
        -b /home:/home \
        -b /var/lib/gtos:/var/lib/gtos \
        -w "$(pwd)" \
        /usr/bin/env \
            DISPLAY="$DISPLAY" \
            WINEPREFIX="$PREFIX" \
            WINEDEBUG=-all \
            WINEDLLOVERRIDES="mscoree,mshtml=" \
            LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
            "/usr/bin/$WBIN" "$@"
}

do_setup_apk() {
    # В live-overlay обычно мало места — apk wine часто не влезает
    free=$(overlay_free_mb || echo 0)
    log "free on /: ${free}MB"
    if [ "${free:-0}" -lt 400 ]; then
        log "мало места на overlay для apk wine — пропускаю"
        return 1
    fi
    mkdir -p /var/lib/gtos/apk-cache /etc/apk
    BRANCH=$(cat /etc/alpine-release 2>/dev/null | cut -d. -f1,2)
    [ -n "$BRANCH" ] || BRANCH=v3.20
    case "$BRANCH" in
        v*) ;;
        *) BRANCH=v3.20 ;;
    esac
    # community обязателен для wine
    printf '%s\n' \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/main" \
        "https://dl-cdn.alpinelinux.org/alpine/${BRANCH}/community" \
        > /etc/apk/repositories
    apk update --cache-dir /var/lib/gtos/apk-cache >>"$LOG" 2>&1 || true
    if ! apk add --no-progress --cache-dir /var/lib/gtos/apk-cache wine >>"$LOG" 2>&1; then
        apk add --no-progress --cache-dir /var/lib/gtos/apk-cache wine-staging >>"$LOG" 2>&1 || true
    fi
    host_wine >/dev/null 2>&1
}

do_setup_glibc() {
    [ -x /usr/bin/gtos-glibc-run ] || { log "нет gtos-glibc-run"; return 1; }
    log "glibc root setup…"
    /usr/bin/gtos-glibc-run --setup >>"$LOG" 2>&1 || true
    [ -d "$GLIBC_ROOT" ] || { log "нет $GLIBC_ROOT"; return 1; }
    command -v proot >/dev/null 2>&1 || { log "нет proot"; return 1; }
    [ -f /etc/resolv.conf ] && cp -f /etc/resolv.conf "$GLIBC_ROOT/etc/resolv.conf" 2>/dev/null || true
    if glibc_has_wine; then
        log "glibc wine уже есть"
        return 0
    fi
    log "apt install wine в glibc-root (на диске данных)…"
    # ubuntu-base часто без universe — без него пакета wine нет
    if ! proot --kill-on-exit \
        -r "$GLIBC_ROOT" \
        -b /dev -b /proc -b /sys -b /tmp:/tmp \
        -b /etc/resolv.conf:/etc/resolv.conf \
        /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        /bin/bash -c '
set -e
. /etc/os-release
CODENAME=${VERSION_CODENAME:-jammy}
cat >/etc/apt/sources.list <<EOF
deb http://archive.ubuntu.com/ubuntu ${CODENAME} main universe multiverse
deb http://archive.ubuntu.com/ubuntu ${CODENAME}-updates main universe multiverse
deb http://security.ubuntu.com/ubuntu ${CODENAME}-security main universe multiverse
EOF
dpkg --add-architecture i386 || true
apt-get update -y
apt-get install -y --no-install-recommends \
  wine64 wine32 wine winetricks cabextract \
  libgl1 libasound2 libx11-6 libfreetype6 fonts-dejavu-core \
  || apt-get install -y --no-install-recommends wine64 wine winetricks cabextract \
  || apt-get install -y wine
rm -rf /var/lib/apt/lists/*
' >>"$LOG" 2>&1; then
        log "apt wine FAILED — хвост:"
        tail -n 30 "$LOG" | while read -r line; do log "  $line"; done
        return 1
    fi
    glibc_has_wine
}

init_prefix() {
    mkdir -p "$PREFIX"
    export DISPLAY="${DISPLAY:-:0}"
    export WINEPREFIX="$PREFIX"
    export WINEDEBUG=-all
    if W=$(host_wine); then
        "$W" wineboot -i >>"$LOG" 2>&1 || "$W" wineboot -u >>"$LOG" 2>&1 || true
        if command -v winetricks >/dev/null 2>&1; then
            winetricks -q vcrun2019 corefonts >>"$LOG" 2>&1 || \
            winetricks -q vcrun2015 corefonts >>"$LOG" 2>&1 || true
        fi
    elif glibc_has_wine; then
        ( cd /tmp && invoke_glibc_wine wineboot -i ) >>"$LOG" 2>&1 || true
        # winetricks внутри glibc, если есть
        if [ -x "$GLIBC_ROOT/usr/bin/winetricks" ]; then
            ( cd /tmp && invoke_glibc_wine winetricks -q vcrun2019 corefonts ) >>"$LOG" 2>&1 || true
        fi
    fi
    date -Iseconds >"$MARKER" 2>/dev/null || echo ok >"$MARKER"
}

do_setup() {
    : >"$LOG"
    rm -f "$READY" "$FAIL"
    log "setup start"
    # Сначала glibc на data-диске — основной путь
    if ! glibc_has_wine; then
        do_setup_glibc && log "glibc wine OK" || log "glibc wine не встал"
    else
        log "glibc wine уже готов"
    fi
    # apk — только если ещё нет никакого wine и есть место
    if ! host_wine >/dev/null 2>&1 && ! glibc_has_wine; then
        do_setup_apk || log "apk wine пропущен/не встал"
    fi
    if host_wine >/dev/null 2>&1 || glibc_has_wine; then
        init_prefix
        echo ok >"$READY"
        log "setup OK"
        tail -n 20 "$LOG" > /tmp/gtos-wine-tail.txt 2>/dev/null || true
        return 0
    fi
    echo fail >"$FAIL"
    log "setup FAIL"
    tail -n 40 "$LOG" > /tmp/gtos-wine-tail.txt 2>/dev/null || true
    return 1
}

if [ "${1:-}" = "--setup" ]; then
    do_setup
    exit $?
fi

if [ "${1:-}" = "--status" ]; then
    if host_wine >/dev/null 2>&1 || glibc_has_wine; then echo ready; exit 0; fi
    echo missing
    exit 1
fi

FILE=${1:-}
[ -n "$FILE" ] || { echo "usage: gtos-wine-run <file.exe>" >&2; exit 2; }
shift
FILE=$(readlink -f "$FILE" 2>/dev/null || echo "$FILE")
[ -e "$FILE" ] || { log "нет файла: $FILE"; exit 1; }

: >>"$LOG" 2>/dev/null || : >"$LOG"
log "launch: $FILE"

if ! host_wine >/dev/null 2>&1 && ! glibc_has_wine; then
    do_setup || exit 1
fi

mkdir -p "$PREFIX"
export DISPLAY="${DISPLAY:-:0}"
export WINEPREFIX="$PREFIX"
export WINEDEBUG=-all
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree,mshtml=}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"

DIR=$(dirname "$FILE")
BASE=$(basename "$FILE")
cd "$DIR" || true
low=$(printf '%s' "$BASE" | tr 'A-Z' 'a-z')
log "cwd=$(pwd) display=$DISPLAY prefix=$PREFIX"

set +e
rc=1
if W=$(host_wine); then
    case "$low" in
        *.msi) "$W" msiexec /i "$FILE" "$@" >>"$LOG" 2>&1; rc=$? ;;
        *.bat|*.cmd) "$W" cmd /c "$FILE" "$@" >>"$LOG" 2>&1; rc=$? ;;
        *)
            "$W" start /unix "$FILE" "$@" >>"$LOG" 2>&1; rc=$?
            [ "$rc" -eq 0 ] || { "$W" "$FILE" "$@" >>"$LOG" 2>&1; rc=$?; }
            ;;
    esac
elif glibc_has_wine; then
    case "$low" in
        *.msi) invoke_glibc_wine msiexec /i "$FILE" "$@" >>"$LOG" 2>&1; rc=$? ;;
        *.bat|*.cmd) invoke_glibc_wine cmd /c "$FILE" "$@" >>"$LOG" 2>&1; rc=$? ;;
        *)
            invoke_glibc_wine start /unix "$FILE" "$@" >>"$LOG" 2>&1; rc=$?
            [ "$rc" -eq 0 ] || { invoke_glibc_wine "$FILE" "$@" >>"$LOG" 2>&1; rc=$?; }
            ;;
    esac
else
    log "нет wine"
    rc=127
fi
set -e
log "exit=$rc"
tail -n 50 "$LOG" > /tmp/gtos-wine-tail.txt 2>/dev/null || true
exit "$rc"
