#!/bin/sh
# Запуск GUI от обычного пользователя.
# Usage: gtos-runuser <user> <logfile> -- <command> [args...]
U=${1:-misha}
LOG=${2:-/tmp/gtos-runuser.log}
shift 2
[ "$1" = "--" ] && shift
if [ -z "$1" ]; then
    echo "usage: gtos-runuser USER LOG -- CMD [ARGS...]" >&2
    exit 2
fi

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOME_DIR=/home/$U
mkdir -p "$HOME_DIR" "/tmp/runtime-$U" 2>/dev/null || true
if ! grep -q "^$U:" /etc/passwd 2>/dev/null; then
    echo "$U:x:1000:1000:$U:$HOME_DIR:/bin/sh" >> /etc/passwd
fi
if ! grep -q "^$U:" /etc/group 2>/dev/null; then
    echo "$U:x:1000:" >> /etc/group
fi
chown -R "$U:$U" "$HOME_DIR" "/tmp/runtime-$U" 2>/dev/null || true
chmod 700 "/tmp/runtime-$U" 2>/dev/null || true

export DISPLAY="${DISPLAY:-:0}"
export HOME="$HOME_DIR"
export USER="$U"
export LOGNAME="$U"
export XDG_RUNTIME_DIR="/tmp/runtime-$U"
export MOZ_DISABLE_CONTENT_SANDBOX=1
export MOZ_DISABLE_GMP_SANDBOX=1
export MOZ_DISABLE_RDD_SANDBOX=1
export MOZ_DISABLE_GPU_SANDBOX=1
export MOZ_ENABLE_WAYLAND=0
export MOZ_WEBRENDER=0
export MOZ_ALLOW_DOWNGRADE=1
export MOZ_CRASHREPORTER_DISABLE=1
export MOZ_FORCE_GFX_SW=1
export GDK_BACKEND=x11
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export NO_AT_BRIDGE=1

if [ -f /root/.Xauthority ]; then
    cp -f /root/.Xauthority "$HOME_DIR/.Xauthority" 2>/dev/null || true
    chown "$U:$U" "$HOME_DIR/.Xauthority" 2>/dev/null || true
    export XAUTHORITY="$HOME_DIR/.Xauthority"
fi
xhost +SI:localuser:"$U" >/dev/null 2>&1 || xhost +local: >/dev/null 2>&1 || true

{
    echo "gtos-runuser: from=$(id -u) to=$U cmd=$*"
    # Alpine: su-exec в /sbin
    if [ -x /sbin/su-exec ]; then
        echo "via /sbin/su-exec"
        exec /sbin/su-exec "$U" "$@"
    fi
    if command -v su-exec >/dev/null 2>&1; then
        echo "via su-exec PATH"
        exec su-exec "$U" "$@"
    fi
    if command -v setpriv >/dev/null 2>&1; then
        UIDN=$(id -u "$U" 2>/dev/null || echo 1000)
        GIDN=$(id -g "$U" 2>/dev/null || echo 1000)
        echo "via setpriv $UIDN:$GIDN"
        exec setpriv --reuid="$UIDN" --regid="$GIDN" -- "$@"
    fi
    WRAP=/tmp/gtos-runuser-wrap-$$.sh
    CMD=
    for a in "$@"; do
        CMD="$CMD $(printf '%s' "$a" | sed "s/'/'\\\\''/g; s/^/'/; s/\$/'/")"
    done
    cat > "$WRAP" <<EOF
#!/bin/sh
export HOME='$HOME_DIR' USER='$U' LOGNAME='$U' DISPLAY='$DISPLAY'
export XDG_RUNTIME_DIR='/tmp/runtime-$U'
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export MOZ_DISABLE_CONTENT_SANDBOX=1 GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1
cd "\$HOME" 2>/dev/null || true
exec $CMD
EOF
    chmod 755 "$WRAP"
    chown "$U:$U" "$WRAP" 2>/dev/null || true
    echo "via su"
    exec su "$U" -c "$WRAP"
} >>"$LOG" 2>&1
echo "gtos-runuser: failed" >>"$LOG"
exit 1
