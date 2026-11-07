#!/bin/sh
# Проверка железа для GT/OS: Wi‑Fi, звук, GPU, Bluetooth, USB/установка
# Пишет отчёт в stdout и опционально в файл (аргумент 1)

OUT=${1:-}
TMP=$(mktemp /tmp/gtos-hw.XXXXXX 2>/dev/null || echo /tmp/gtos-hwcheck.txt)
{
    echo "GT/OS hardware check · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "===="
    echo "CPU: $(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //')"
    echo "MEM: $(awk '/MemTotal/{printf "%.1f GiB", $2/1024/1024}' /proc/meminfo 2>/dev/null)"
    echo "EFI: $([ -d /sys/firmware/efi ] && echo yes || echo no)"
    echo "==== Wi-Fi"
    WL=$(ls /sys/class/net 2>/dev/null | awk '/^wl|^wlan/{print; exit}')
    if [ -n "$WL" ]; then
        echo "OK iface=$WL"
        iwconfig "$WL" 2>/dev/null | head -n 4 || ip link show "$WL" 2>/dev/null | head -n 2
    else
        echo "WARN no wireless iface (часто нормально в QEMU)"
    fi
    echo "==== Sound"
    if [ -d /proc/asound ] && ls /proc/asound/cards >/dev/null 2>&1; then
        echo "OK cards:"
        cat /proc/asound/cards 2>/dev/null
        aplay -l 2>/dev/null | head -n 8 || true
    else
        echo "WARN no ALSA cards"
    fi
    echo "==== GPU"
    if command -v lspci >/dev/null 2>&1; then
        lspci 2>/dev/null | grep -iE 'vga|3d|display' || echo "WARN no VGA line"
    else
        echo "INFO lspci missing"
        cat /proc/device-tree/model 2>/dev/null || true
    fi
    echo "==== Bluetooth"
    if command -v bluetoothctl >/dev/null 2>&1; then
        bluetoothctl show 2>/dev/null | head -n 8 || echo "WARN no adapter"
    elif [ -d /sys/class/bluetooth ]; then
        ls /sys/class/bluetooth 2>/dev/null || echo "WARN empty bluetooth class"
    else
        echo "WARN no bluetooth stack/adapter"
    fi
    echo "==== USB / install media"
    lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT 2>/dev/null | head -n 20 || true
    if [ -f /usr/share/gtos/boot/vmlinuz ] || [ -f /boot/vmlinuz ]; then
        echo "OK kernel payload present"
    else
        echo "WARN kernel payload missing"
    fi
    if [ -x /usr/bin/gtos-install ]; then
        echo "OK gtos-install present"
    else
        echo "WARN gtos-install missing"
    fi
    echo "===="
    echo "GTOS_HWCHECK_DONE"
} > "$TMP"

cat "$TMP"
if [ -n "$OUT" ]; then
    mkdir -p "$(dirname "$OUT")" 2>/dev/null || true
    cp -f "$TMP" "$OUT"
fi
rm -f "$TMP" 2>/dev/null || true
exit 0
