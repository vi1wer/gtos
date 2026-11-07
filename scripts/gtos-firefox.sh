#!/bin/sh
# Надёжный запуск Firefox в GT/OS (QEMU / software GL / без root-профиля).
# Без dbus-run-session: в минимальном образе он часто сразу падает и Firefox «не стартует».
[ -c /dev/ttyS0 ] && echo "GTOS_FIREFOX_ENTER pid=$$ uid=$(id -u 2>/dev/null)" >/dev/ttyS0 2>/dev/null
LOG=/tmp/gtos-firefox.log
LOG2=/var/lib/gtos/firefox-last.log
mkdir -p /var/lib/gtos /tmp /dev/shm 2>/dev/null || true
chmod 1777 /tmp /dev/shm 2>/dev/null || true

U=$(tr -d '\r\n' < /var/lib/gtos/username 2>/dev/null || true)
[ -n "$U" ] || U=misha
U=$(printf '%s' "$U" | tr -cd 'a-zA-Z0-9._-')
[ -n "$U" ] || U=misha

HOME_DIR=/home/$U
PROF_DIR=$HOME_DIR/.mozilla/firefox
PROF=$PROF_DIR/gtos.default
BIN=/usr/bin/firefox
[ -x "$BIN" ] || BIN=/usr/lib/firefox/firefox

: >"$LOG"
exec >>"$LOG" 2>&1
echo "=== gtos-firefox $(date) ==="
echo "user=$U bin=$BIN display=${DISPLAY:-:0} id=$(id -u)/$(id -un)"
[ -c /dev/ttyS0 ] && echo "GTOS_FIREFOX_BEGIN $U" >/dev/ttyS0

if [ ! -x "$BIN" ]; then
    echo "FATAL: firefox missing"
    cp -f "$LOG" "$LOG2" 2>/dev/null || true
    [ -c /dev/ttyS0 ] && echo GTOS_FIREFOX_FAIL >/dev/ttyS0
    exit 127
fi

# пользователь в passwd/group
if ! grep -q "^$U:" /etc/passwd 2>/dev/null; then
    echo "$U:x:1000:1000:$U:$HOME_DIR:/bin/sh" >> /etc/passwd
fi
if ! grep -q "^$U:" /etc/group 2>/dev/null; then
    echo "$U:x:1000:" >> /etc/group
fi

# machine-id нужен части библиотек
if [ ! -s /etc/machine-id ]; then
    printf 'gtos%024d\n' "$$" > /etc/machine-id 2>/dev/null || true
fi

mkdir -p "$PROF" "$HOME_DIR" "/tmp/runtime-$U" 2>/dev/null || true
rm -f "$PROF"/lock "$PROF"/.parentlock "$PROF"/*.lock 2>/dev/null || true

# profiles.ini обязателен — без него Firefox часто сразу выходит
cat > "$PROF_DIR/profiles.ini" <<EOF
[General]
StartWithLastProfile=1
Version=2

[Profile0]
Name=gtos
IsRelative=1
Path=gtos.default
Default=1
EOF

# свежие prefs под software GL + больше памяти (QEMU 14 ГБ)
cat > "$PROF/prefs.js" <<'EOF'
// GT/OS software profile
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.tabs.remote.autostart", true);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("app.update.enabled", false);
user_pref("app.update.auto", false);
user_pref("layers.acceleration.disabled", true);
user_pref("layers.acceleration.force-enabled", false);
user_pref("gfx.webrender.all", false);
user_pref("gfx.webrender.enabled", false);
user_pref("gfx.webrender.software", true);
user_pref("gfx.webrender.software.opengl", false);
user_pref("media.hardware-video-decoding.enabled", false);
user_pref("media.ffmpeg.vaapi.enabled", false);
user_pref("security.sandbox.content.level", 0);
user_pref("security.sandbox.gpu.level", 0);
user_pref("browser.startup.homepage", "about:blank");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("browser.aboutwelcome.enabled", false);
// Память: больше кэшей, меньше процессов (TCG плохо переносит кучу content-процессов)
user_pref("dom.ipc.processCount", 2);
user_pref("dom.ipc.processCount.webIsolated", 1);
user_pref("browser.cache.memory.enable", true);
user_pref("browser.cache.memory.capacity", 1048576);
user_pref("browser.cache.memory.max_entry_size", 102400);
user_pref("browser.cache.disk.enable", true);
user_pref("browser.cache.disk.capacity", 1048576);
user_pref("media.memory_cache_max_size", 262144);
user_pref("media.memory_caches_combined_limit_kb", 1048576);
user_pref("image.mem.max_decoded_image_kb", 524288);
user_pref("image.mem.surfacecache.max_size_kb", 1048576);
user_pref("javascript.options.mem.high_water_mark", 256);
user_pref("javascript.options.mem.gc_allocation_threshold_mb", 64);
user_pref("browser.sessionhistory.max_total_viewers", 8);
user_pref("network.http.max-connections", 48);
user_pref("network.http.max-persistent-connections-per-server", 8);
EOF

# НЕ chown -R весь $HOME — на больших дисках это минуты и «Firefox не стартует»
chown -R "$U:$U" "$PROF_DIR" "/tmp/runtime-$U" 2>/dev/null || true
chown "$U:$U" "$HOME_DIR" 2>/dev/null || true
chmod 700 "/tmp/runtime-$U" 2>/dev/null || true
chmod -R u+rwX "$PROF_DIR" 2>/dev/null || true

export DISPLAY="${DISPLAY:-:0}"
export HOME="$HOME_DIR"
export USER="$U"
export LOGNAME="$U"
export XDG_RUNTIME_DIR="/tmp/runtime-$U"
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export MOZ_DISABLE_CONTENT_SANDBOX=1
export MOZ_DISABLE_GMP_SANDBOX=1
export MOZ_DISABLE_RDD_SANDBOX=1
export MOZ_DISABLE_GPU_SANDBOX=1
export MOZ_DBUS_REMOTE=0
export MOZ_ENABLE_WAYLAND=0
export MOZ_WEBRENDER=0
export MOZ_ALLOW_DOWNGRADE=1
export MOZ_CRASHREPORTER_DISABLE=1
export MOZ_FORCE_DISABLE_E10S=
export GDK_BACKEND=x11
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export NO_AT_BRIDGE=1
export MOZ_FORCE_GFX_SW=1

# доступ к X
if [ -f /root/.Xauthority ]; then
    cp -f /root/.Xauthority "$HOME_DIR/.Xauthority" 2>/dev/null || true
    chown "$U:$U" "$HOME_DIR/.Xauthority" 2>/dev/null || true
    export XAUTHORITY="$HOME_DIR/.Xauthority"
elif [ -f "$HOME_DIR/.Xauthority" ]; then
    export XAUTHORITY="$HOME_DIR/.Xauthority"
fi
xhost +SI:localuser:"$U" >/dev/null 2>&1 || xhost +local: >/dev/null 2>&1 || xhost + >/dev/null 2>&1 || true

ff_alive() {
    pgrep -x firefox >/dev/null 2>&1 && return 0
    pgrep -x firefox-bin >/dev/null 2>&1 && return 0
    pgrep -f '[/]usr/lib/firefox/firefox' >/dev/null 2>&1 && return 0
    return 1
}

# Уже запущен — не плодим вторую копию
if ff_alive; then
    echo "already running"
    cp -f "$LOG" "$LOG2" 2>/dev/null || true
    [ -c /dev/ttyS0 ] && echo GTOS_FIREFOX_OK >/dev/ttyS0
    exit 0
fi

start_ff() {
    # $* = команда запуска (su-exec … firefox …)
    echo "try: $*"
    "$@" >>"$LOG" 2>&1 &
    FPID=$!
    # На TCG Firefox поднимается долго — ждём до ~20 с
    i=0
    while [ "$i" -lt 20 ]; do
        if ff_alive; then
            echo "OK pid=$FPID after ${i}s"
            cp -f "$LOG" "$LOG2" 2>/dev/null || true
            [ -c /dev/ttyS0 ] && echo GTOS_FIREFOX_OK >/dev/ttyS0
            wait "$FPID"
            echo "firefox exit=$?"
            cp -f "$LOG" "$LOG2" 2>/dev/null || true
            exit 0
        fi
        # процесс-обёртка умерла раньше firefox
        if ! kill -0 "$FPID" 2>/dev/null; then
            # firefox мог успеть отделиться
            sleep 1
            if ff_alive; then
                echo "OK detached"
                cp -f "$LOG" "$LOG2" 2>/dev/null || true
                [ -c /dev/ttyS0 ] && echo GTOS_FIREFOX_OK >/dev/ttyS0
                exit 0
            fi
            echo "wrapper exited early"
            break
        fi
        sleep 1
        i=$((i + 1))
    done
    echo "FAILED quick-exit / timeout"
    return 1
}

FF_ARGS="-no-remote --allow-downgrade -profile $PROF"

env_prefix() {
    # печатает env VAR=… для su-exec
    printf '%s' "env HOME=$HOME_DIR USER=$U LOGNAME=$U DISPLAY=$DISPLAY"
    printf '%s' " XDG_RUNTIME_DIR=/tmp/runtime-$U"
    [ -n "${XAUTHORITY:-}" ] && printf '%s' " XAUTHORITY=$XAUTHORITY"
    printf '%s' " PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    printf '%s' " MOZ_DISABLE_CONTENT_SANDBOX=1 MOZ_DISABLE_GMP_SANDBOX=1 MOZ_DISABLE_RDD_SANDBOX=1 MOZ_DISABLE_GPU_SANDBOX=1"
    printf '%s' " MOZ_ENABLE_WAYLAND=0 MOZ_WEBRENDER=0 MOZ_ALLOW_DOWNGRADE=1 MOZ_CRASHREPORTER_DISABLE=1 MOZ_FORCE_GFX_SW=1"
    printf '%s' " GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe MESA_LOADER_DRIVER_OVERRIDE=llvmpipe NO_AT_BRIDGE=1"
}

# 1) su-exec (Alpine: /sbin/su-exec)
if [ -x /sbin/su-exec ]; then
    echo "via /sbin/su-exec"
    # shellcheck disable=SC2086
    if start_ff /sbin/su-exec "$U" $(env_prefix) "$BIN" $FF_ARGS; then
        exit 0
    fi
fi
if command -v su-exec >/dev/null 2>&1; then
    echo "via su-exec PATH"
    # shellcheck disable=SC2086
    if start_ff su-exec "$U" $(env_prefix) "$BIN" $FF_ARGS; then
        exit 0
    fi
fi

# 2) gtos-runuser
if [ -x /usr/bin/gtos-runuser ]; then
    echo "via gtos-runuser"
    # shellcheck disable=SC2086
    if start_ff /usr/bin/gtos-runuser "$U" "$LOG" -- "$BIN" $FF_ARGS; then
        exit 0
    fi
fi

# 3) busybox su -c
if command -v su >/dev/null 2>&1; then
    echo "via su"
    WRAP=/tmp/gtos-ff-wrap-$$.sh
    cat > "$WRAP" <<EOF
#!/bin/sh
export HOME='$HOME_DIR' USER='$U' LOGNAME='$U' DISPLAY='$DISPLAY'
export XDG_RUNTIME_DIR='/tmp/runtime-$U'
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export MOZ_DISABLE_CONTENT_SANDBOX=1 MOZ_DISABLE_GMP_SANDBOX=1 MOZ_DISABLE_RDD_SANDBOX=1 MOZ_DISABLE_GPU_SANDBOX=1
export MOZ_ENABLE_WAYLAND=0 MOZ_WEBRENDER=0 MOZ_ALLOW_DOWNGRADE=1 MOZ_CRASHREPORTER_DISABLE=1 MOZ_FORCE_GFX_SW=1
export GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe MESA_LOADER_DRIVER_OVERRIDE=llvmpipe NO_AT_BRIDGE=1
[ -n '${XAUTHORITY:-}' ] && export XAUTHORITY='${XAUTHORITY:-}'
cd "\$HOME" || true
exec '$BIN' $FF_ARGS
EOF
    chmod 755 "$WRAP"
    chown "$U:$U" "$WRAP" 2>/dev/null || true
    if start_ff su "$U" -c "$WRAP"; then
        exit 0
    fi
fi

echo "FATAL: all launch methods failed"
ls -la "$BIN" "$PROF_DIR" 2>&1 || true
ldd "$BIN" 2>&1 | head -n 40 || true
cp -f "$LOG" "$LOG2" 2>/dev/null || true
if [ -c /dev/ttyS0 ]; then
    echo GTOS_FIREFOX_FAIL >/dev/ttyS0
    tail -n 100 "$LOG" >/dev/ttyS0 2>/dev/null || true
fi
exit 1
