#!/bin/sh
# GT Orbit — браузер GT/OS на движке Chromium
[ -c /dev/ttyS0 ] && echo "GTOS_ORBIT_ENTER pid=$$" >/dev/ttyS0 2>/dev/null
LOG=/tmp/gtos-orbit.log
mkdir -p /tmp /var/lib/gtos /dev/shm 2>/dev/null || true
chmod 1777 /tmp /dev/shm 2>/dev/null || true
: >"$LOG"
exec >>"$LOG" 2>&1
echo "=== gtos-orbit $(date) ==="

U=$(tr -d '\r\n' < /var/lib/gtos/username 2>/dev/null || true)
[ -n "$U" ] || U=misha
U=$(printf '%s' "$U" | tr -cd 'a-zA-Z0-9._-')
[ -n "$U" ] || U=misha
HOME_DIR=/home/$U
PROF="$HOME_DIR/.config/gt-orbit"
mkdir -p "$PROF" "/tmp/runtime-$U" 2>/dev/null || true
chown -R "$U:$U" "$PROF" "/tmp/runtime-$U" 2>/dev/null || true

BIN=""
for c in /usr/bin/chromium-browser /usr/bin/chromium /usr/lib/chromium/chromium /usr/bin/chrome; do
    if [ -x "$c" ]; then
        BIN=$c
        break
    fi
done
if [ -z "$BIN" ]; then
    echo "FATAL: chromium missing"
    [ -c /dev/ttyS0 ] && echo GTOS_ORBIT_NEED_CHROMIUM >/dev/ttyS0
    exit 127
fi

export DISPLAY="${DISPLAY:-:0}"
export HOME="$HOME_DIR"
export USER="$U"
export LOGNAME="$U"
export XDG_RUNTIME_DIR="/tmp/runtime-$U"
export LIBGL_ALWAYS_SOFTWARE=1
export GDK_BACKEND=x11
xhost +SI:localuser:"$U" >/dev/null 2>&1 || xhost +local: >/dev/null 2>&1 || true

ARGS="--user-data-dir=$PROF --class=GTOrbit --name=GT Orbit --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer=false"

if pgrep -f '[c]hromium' >/dev/null 2>&1 || pgrep -f 'user-data-dir=.*/gt-orbit' >/dev/null 2>&1; then
    echo "already running"
    [ -c /dev/ttyS0 ] && echo GTOS_ORBIT_OK >/dev/ttyS0
    exit 0
fi

run() {
    echo "try: $*"
    "$@" &
    FPID=$!
    i=0
    while [ "$i" -lt 15 ]; do
        if pgrep -f 'user-data-dir=.*/gt-orbit' >/dev/null 2>&1 || pgrep -x chromium >/dev/null 2>&1 || pgrep -x chromium-browser >/dev/null 2>&1; then
            echo "OK"
            [ -c /dev/ttyS0 ] && echo GTOS_ORBIT_OK >/dev/ttyS0
            wait "$FPID" 2>/dev/null || true
            exit 0
        fi
        kill -0 "$FPID" 2>/dev/null || break
        sleep 1
        i=$((i + 1))
    done
    return 1
}

# shellcheck disable=SC2086
if [ -x /sbin/su-exec ]; then
    run /sbin/su-exec "$U" env HOME="$HOME_DIR" USER="$U" DISPLAY="$DISPLAY" \
        XDG_RUNTIME_DIR="/tmp/runtime-$U" LIBGL_ALWAYS_SOFTWARE=1 GDK_BACKEND=x11 \
        "$BIN" $ARGS && exit 0
fi
if [ -x /usr/bin/gtos-runuser ]; then
    # shellcheck disable=SC2086
    run /usr/bin/gtos-runuser "$U" "$LOG" -- "$BIN" $ARGS && exit 0
fi
# shellcheck disable=SC2086
run "$BIN" $ARGS && exit 0

echo "FATAL: launch failed"
[ -c /dev/ttyS0 ] && echo GTOS_ORBIT_FAIL >/dev/ttyS0
exit 1
