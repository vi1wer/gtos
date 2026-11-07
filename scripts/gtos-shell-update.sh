#!/bin/sh
# Обновление оболочки GT/OS: ядро/initrd + QML с носителя или payload.
# Usage: gtos-shell-update.sh [source_dir]
# source: каталог с boot/vmlinuz + boot/initrd.gz и опционально qml/Main.qml

set -e
export PATH=/sbin:/usr/sbin:/bin:/usr/bin
CHECK_ONLY=0
WANT_NET=0
SRC=""
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --network|--net) WANT_NET=1 ;;
        *) SRC=$arg ;;
    esac
done
GTOS_VER=${GTOS_VERSION:-1.5.6}

# Канал обновлений: /var/lib/gtos/update-channel (url=...)
channel_url() {
    U=""
    if [ -f /var/lib/gtos/update-channel ]; then
        U=$(awk -F= '/^url=/{print substr($0,5); exit}' /var/lib/gtos/update-channel | tr -d '\r')
    fi
    if [ -z "$U" ] && [ -n "${GTOS_UPDATE_URL:-}" ]; then
        U=$GTOS_UPDATE_URL
    fi
    printf '%s' "$U"
}

fetch_network_payload() {
    BASE=$(channel_url)
    [ -n "$BASE" ] || return 1
    BASE=${BASE%/}
    DEST=/usr/share/gtos/update-payload
    mkdir -p "$DEST/boot" "$DEST/qml"
    echo "GTOS_SHELL_UPDATE_NET $BASE"
    curl -fsSL --max-time 20 "$BASE/gtos-version" -o "$DEST/gtos-version" 2>/tmp/gtos-upd-net.log || \
        curl -fsSL --max-time 20 "$BASE/boot/gtos-version" -o "$DEST/gtos-version" 2>>/tmp/gtos-upd-net.log || return 1
    REMOTE=$(head -n1 "$DEST/gtos-version" | tr -d '\r\n')
    LOCAL=$(head -n1 /var/lib/gtos/version 2>/dev/null | tr -d '\r\n')
    [ -z "$LOCAL" ] && LOCAL=$(head -n1 /usr/share/gtos/version 2>/dev/null | tr -d '\r\n')
    echo "GTOS_SHELL_UPDATE_NET_VER remote=$REMOTE local=${LOCAL:-none}"
    if [ "$CHECK_ONLY" = "1" ]; then
        if [ -n "$REMOTE" ] && [ "$REMOTE" != "$LOCAL" ]; then
            echo "GTOS_SHELL_UPDATE_AVAILABLE src=network ver=$REMOTE"
            exit 0
        fi
        echo "GTOS_SHELL_UPDATE_NET_SAME ver=$REMOTE"
        return 0
    fi
    # скачать ядро/initrd/qml при наличии
    curl -fsSL --max-time 120 "$BASE/boot/vmlinuz" -o "$DEST/boot/vmlinuz" 2>>/tmp/gtos-upd-net.log || \
        curl -fsSL --max-time 120 "$BASE/vmlinuz" -o "$DEST/boot/vmlinuz" 2>>/tmp/gtos-upd-net.log || true
    curl -fsSL --max-time 180 "$BASE/boot/initrd.gz" -o "$DEST/boot/initrd.gz" 2>>/tmp/gtos-upd-net.log || \
        curl -fsSL --max-time 180 "$BASE/initrd.gz" -o "$DEST/boot/initrd.gz" 2>>/tmp/gtos-upd-net.log || \
        curl -fsSL --max-time 180 "$BASE/boot/gtos-rootfs.cpio.gz" -o "$DEST/boot/initrd.gz" 2>>/tmp/gtos-upd-net.log || true
    curl -fsSL --max-time 60 "$BASE/qml/Main.qml" -o "$DEST/qml/Main.qml" 2>>/tmp/gtos-upd-net.log || \
        curl -fsSL --max-time 60 "$BASE/usr/share/gtos/qml/Main.qml" -o "$DEST/qml/Main.qml" 2>>/tmp/gtos-upd-net.log || true
    if [ -f "$DEST/boot/vmlinuz" ] && [ -f "$DEST/boot/initrd.gz" ]; then
        SRC=$DEST
        return 0
    fi
    # только QML — всё равно полезно
    if [ -f "$DEST/qml/Main.qml" ]; then
        mkdir -p /usr/share/gtos/qml
        cp -f "$DEST/qml/Main.qml" /usr/share/gtos/qml/Main.qml
        printf '%s\n' "${REMOTE:-$GTOS_VER}" > /var/lib/gtos/version
        echo "GTOS_SHELL_UPDATE_QML_ONLY ver=${REMOTE:-$GTOS_VER}"
        exit 0
    fi
    return 1
}

if [ "$WANT_NET" = "1" ] || [ -n "$(channel_url)" ]; then
    if fetch_network_payload; then
        :
    else
        if [ "$WANT_NET" = "1" ] && [ "$CHECK_ONLY" = "1" ]; then
            echo "GTOS_SHELL_UPDATE_NET_FAIL"
        fi
    fi
fi

find_src() {
    if [ -n "$SRC" ] && [ -f "$SRC/boot/vmlinuz" ]; then
        echo "$SRC"
        return
    fi
    if [ -n "$SRC" ] && [ -f "$SRC/vmlinuz" ]; then
        echo "$SRC"
        return
    fi
    for cand in \
        /usr/share/gtos/update-payload \
        /mnt/cdrom \
        /media/cdrom \
        /run/media/gtos-update \
        /mnt/usb \
        /usr/share/gtos
    do
        if [ -f "$cand/boot/vmlinuz" ] && { [ -f "$cand/boot/initrd.gz" ] || [ -f "$cand/boot/gtos-rootfs.cpio.gz" ]; }; then
            echo "$cand"
            return
        fi
        if [ -f "$cand/vmlinuz" ] && [ -f "$cand/initrd.gz" ]; then
            echo "$cand"
            return
        fi
    done
    # попробовать смонтировать ISO/USB
    mkdir -p /mnt/cdrom /mnt/usb
    for od in /dev/sr0 /dev/cdrom /dev/dvd; do
        [ -b "$od" ] || continue
        mount -o ro "$od" /mnt/cdrom 2>/dev/null || continue
        if [ -f /mnt/cdrom/boot/vmlinuz ]; then
            echo /mnt/cdrom
            return
        fi
        umount /mnt/cdrom 2>/dev/null || true
    done
    for pd in /dev/sd[a-z]1 /dev/vd[a-z]1 /dev/nvme0n1p1; do
        [ -b "$pd" ] || continue
        mount -o ro "$pd" /mnt/usb 2>/dev/null || continue
        if [ -f /mnt/usb/boot/vmlinuz ]; then
            echo /mnt/usb
            return
        fi
        umount /mnt/usb 2>/dev/null || true
    done
    echo ""
}

ROOT_SRC=$(find_src)
if [ -z "$ROOT_SRC" ]; then
    echo "GTOS_SHELL_UPDATE_NONE"
    exit 3
fi
if [ "$CHECK_ONLY" = "1" ]; then
    VER=""
    [ -f "$ROOT_SRC/gtos-version" ] && VER=$(head -n1 "$ROOT_SRC/gtos-version" | tr -d '\r\n')
    [ -z "$VER" ] && [ -f "$ROOT_SRC/boot/gtos-version" ] && VER=$(head -n1 "$ROOT_SRC/boot/gtos-version" | tr -d '\r\n')
    echo "GTOS_SHELL_UPDATE_AVAILABLE src=$ROOT_SRC ver=${VER:-unknown}"
    exit 0
fi

BOOT_SRC=$ROOT_SRC/boot
if [ ! -f "$BOOT_SRC/vmlinuz" ]; then
    BOOT_SRC=$ROOT_SRC
fi
INITRD=""
if [ -f "$BOOT_SRC/initrd.gz" ]; then
    INITRD="$BOOT_SRC/initrd.gz"
elif [ -f "$BOOT_SRC/gtos-rootfs.cpio.gz" ]; then
    INITRD="$BOOT_SRC/gtos-rootfs.cpio.gz"
fi
if [ ! -f "$BOOT_SRC/vmlinuz" ] || [ -z "$INITRD" ]; then
    echo "GTOS_SHELL_UPDATE_BADSRC $ROOT_SRC"
    exit 4
fi

echo "GTOS_SHELL_UPDATE_START $ROOT_SRC"
mkdir -p /boot /usr/share/gtos/boot /usr/share/gtos/qml /var/lib/gtos

# снимок до обновления
STAMP=$(date -u +%Y%m%d-%H%M%S)
SNAP=/var/lib/gtos/update-snapshots/shell-$STAMP
mkdir -p "$SNAP"
cp -f /boot/vmlinuz "$SNAP/" 2>/dev/null || true
cp -f /boot/initrd.gz "$SNAP/" 2>/dev/null || true
cp -f /usr/share/gtos/qml/Main.qml "$SNAP/" 2>/dev/null || true
cp -f /var/lib/gtos/version "$SNAP/os-version.txt" 2>/dev/null || true
echo "shell-$STAMP" > /var/lib/gtos/update-snapshots/latest-shell

cp -f "$BOOT_SRC/vmlinuz" /boot/vmlinuz
cp -f "$INITRD" /boot/initrd.gz
cp -f /boot/vmlinuz /usr/share/gtos/boot/vmlinuz
cp -f /boot/initrd.gz /usr/share/gtos/boot/initrd.gz

# QML: с носителя или из распакованного payload
QML_SRC=""
for q in "$ROOT_SRC/usr/share/gtos/qml/Main.qml" "$ROOT_SRC/qml/Main.qml" /usr/share/gtos/update-payload/qml/Main.qml; do
    if [ -f "$q" ]; then
        QML_SRC=$q
        break
    fi
done
if [ -n "$QML_SRC" ]; then
    cp -f "$QML_SRC" /usr/share/gtos/qml/Main.qml
    echo "GTOS_SHELL_UPDATE_QML $QML_SRC"
fi

# версия с носителя или аргумент окружения
if [ -f "$ROOT_SRC/gtos-version" ]; then
    GTOS_VER=$(head -n1 "$ROOT_SRC/gtos-version" | tr -d '\r\n')
elif [ -f "$ROOT_SRC/boot/gtos-version" ]; then
    GTOS_VER=$(head -n1 "$ROOT_SRC/boot/gtos-version" | tr -d '\r\n')
elif [ -f /usr/share/gtos/version ]; then
    GTOS_VER=$(head -n1 /usr/share/gtos/version | tr -d '\r\n')
fi
printf '%s\n' "$GTOS_VER" > /var/lib/gtos/version
printf '%s\n' "$GTOS_VER" > /usr/share/gtos/version

# ESP, если смонтирован
if mountpoint -q /boot/efi 2>/dev/null || [ -d /boot/efi/EFI ]; then
    mkdir -p /boot/efi/EFI/gtos
    cp -f /boot/vmlinuz /boot/efi/EFI/gtos/vmlinuz 2>/dev/null || true
    cp -f /boot/initrd.gz /boot/efi/EFI/gtos/initrd.gz 2>/dev/null || true
fi

sync
echo "GTOS_SHELL_UPDATE_DONE ver=$GTOS_VER snap=shell-$STAMP"
exit 0
