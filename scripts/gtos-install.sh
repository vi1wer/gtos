#!/bin/sh
# GT/OS installer: GPT+UEFI и/или MBR+BIOS, rootfs, GRUB
# Usage: gtos-install.sh <disk> <username> <fullname> <lang> <bootmode>
# bootmode: auto | uefi | bios | both
# Example: gtos-install.sh sda misha Misha ru auto

set -e
DISK_NAME=$1
USER_NAME=${2:-misha}
FULL_NAME=${3:-Misha}
LANG_CODE=${4:-ru}
BOOT_MODE=${5:-auto}
GTOS_VER=${GTOS_VERSION:-1.6}

if [ -z "$DISK_NAME" ]; then
    echo "ERR: no disk"
    exit 1
fi
DISK="/dev/$DISK_NAME"
if [ ! -b "$DISK" ]; then
    echo "ERR: $DISK not a block device"
    exit 1
fi

echo "GTOS_INSTALL_START $DISK"
export PATH=/sbin:/usr/sbin:/bin:/usr/bin

case "$DISK_NAME" in
    sd*|vd*|nvme*n*) ;;
    *) echo "ERR: refused disk name"; exit 1 ;;
esac

# auto: UEFI firmware → uefi (hybrid GPT), иначе bios (MBR)
if [ "$BOOT_MODE" = "auto" ]; then
    if [ -d /sys/firmware/efi ]; then
        BOOT_MODE=uefi
    else
        BOOT_MODE=bios
    fi
fi
echo "GTOS_INSTALL_BOOTMODE $BOOT_MODE"

# подтянуть EFI-пакеты при наличии сети (на старых ISO)
if [ "$BOOT_MODE" = "uefi" ] || [ "$BOOT_MODE" = "both" ]; then
    command -v grub-install >/dev/null 2>&1 || true
    if ! grub-install --help 2>&1 | grep -q x86_64-efi; then
        apk add --no-cache grub-efi efibootmgr dosfstools 2>/tmp/gtos-apk-efi.log || true
    fi
fi

umount ${DISK}* 2>/dev/null || true
umount /mnt/gtos/boot/efi 2>/dev/null || true
umount /mnt/gtos/boot 2>/dev/null || true
umount /mnt/gtos/efi 2>/dev/null || true
umount /mnt/gtos 2>/dev/null || true

P_EFI=""
P_BOOT=""
P_ROOT=""
P_BIOSGRUB=""

echo "GTOS_INSTALL_PARTITION"
if [ "$BOOT_MODE" = "bios" ]; then
    sfdisk --wipe always "$DISK" <<EOF
label: dos
,512M,L,*
,,L
EOF
    P_BOOT="${DISK}1"
    P_ROOT="${DISK}2"
    if [ -b "${DISK}p1" ]; then
        P_BOOT="${DISK}p1"
        P_ROOT="${DISK}p2"
    fi
else
    # GPT: BIOS boot (hybrid) + ESP + root — грузится и с UEFI, и с legacy
    sfdisk --wipe always "$DISK" <<EOF
label: gpt
size=1MiB, type=21686148-6449-6E6F-744E-656564454649, name=biosboot
size=512MiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name=EFI
type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name=GTOSROOT
EOF
    if [ -b "${DISK}p1" ]; then
        P_BIOSGRUB="${DISK}p1"
        P_EFI="${DISK}p2"
        P_ROOT="${DISK}p3"
    else
        P_BIOSGRUB="${DISK}1"
        P_EFI="${DISK}2"
        P_ROOT="${DISK}3"
    fi
fi

sleep 1
mdev -s 2>/dev/null || true
udevadm settle --timeout=3 2>/dev/null || true

echo "GTOS_INSTALL_FORMAT"
if [ -n "$P_BOOT" ]; then
    mkfs.ext4 -F -L GTOSBOOT "$P_BOOT"
fi
if [ -n "$P_EFI" ]; then
    mkfs.vfat -F32 -n GTOSEFI "$P_EFI"
fi
mkfs.ext4 -F -L GTOSROOT "$P_ROOT"

mkdir -p /mnt/gtos
mount "$P_ROOT" /mnt/gtos
mkdir -p /mnt/gtos/boot /mnt/gtos/boot/efi /mnt/gtos/home /mnt/gtos/var/lib/gtos /mnt/gtos/usr/share/gtos/boot

if [ -n "$P_BOOT" ]; then
    mount "$P_BOOT" /mnt/gtos/boot
    mkdir -p /mnt/gtos/boot/efi
fi
if [ -n "$P_EFI" ]; then
    mount "$P_EFI" /mnt/gtos/boot/efi
fi

echo "GTOS_INSTALL_COPY"
tar -C / --one-file-system \
    --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./tmp \
    --exclude=./run --exclude=./mnt --exclude=./data --exclude=./media \
    --exclude=./boot \
    -cf - . 2>/dev/null | tar -C /mnt/gtos -xf - 2>/dev/null || {
    for d in bin sbin etc usr lib lib64 var opt root; do
        [ -e "/$d" ] || continue
        mkdir -p "/mnt/gtos/$d"
        cp -a "/$d/." "/mnt/gtos/$d/" 2>/dev/null || true
    done
}

mkdir -p /mnt/gtos/proc /mnt/gtos/sys /mnt/gtos/dev /mnt/gtos/tmp /mnt/gtos/run /mnt/gtos/mnt /mnt/gtos/home /mnt/gtos/var/lib/gtos /mnt/gtos/usr/share/gtos/boot /mnt/gtos/boot/efi

# ядро + initrd
SRC_BOOT=""
for cand in /mnt/cdrom/boot /media/cdrom/boot /run/media/boot /usr/share/gtos/boot /boot; do
    if [ -f "$cand/vmlinuz" ] && { [ -f "$cand/initrd.gz" ] || [ -f "$cand/gtos-rootfs.cpio.gz" ]; }; then
        SRC_BOOT=$cand
        break
    fi
    if [ -f "$cand/vmlinuz" ]; then
        SRC_BOOT=$cand
        break
    fi
done
if [ -z "$SRC_BOOT" ]; then
    mkdir -p /mnt/cdrom
    for od in /dev/sr0 /dev/cdrom /dev/dvd; do
        if [ -b "$od" ] && mount -o ro "$od" /mnt/cdrom 2>/dev/null; then
            if [ -f /mnt/cdrom/boot/vmlinuz ]; then
                SRC_BOOT=/mnt/cdrom/boot
                break
            fi
            umount /mnt/cdrom 2>/dev/null || true
        fi
    done
fi

if [ -n "$SRC_BOOT" ]; then
    cp -f "$SRC_BOOT"/vmlinuz /mnt/gtos/boot/vmlinuz 2>/dev/null || true
    if [ -f "$SRC_BOOT/initrd.gz" ]; then
        cp -f "$SRC_BOOT/initrd.gz" /mnt/gtos/boot/initrd.gz
    elif [ -f "$SRC_BOOT/gtos-rootfs.cpio.gz" ]; then
        cp -f "$SRC_BOOT/gtos-rootfs.cpio.gz" /mnt/gtos/boot/initrd.gz
    fi
fi
[ -f /usr/share/gtos/boot/vmlinuz ] && [ ! -f /mnt/gtos/boot/vmlinuz ] && cp -f /usr/share/gtos/boot/vmlinuz /mnt/gtos/boot/vmlinuz
[ -f /usr/share/gtos/boot/initrd.gz ] && [ ! -f /mnt/gtos/boot/initrd.gz ] && cp -f /usr/share/gtos/boot/initrd.gz /mnt/gtos/boot/initrd.gz

if [ ! -f /mnt/gtos/boot/vmlinuz ] || [ ! -f /mnt/gtos/boot/initrd.gz ]; then
    echo "ERR: kernel/initrd missing — загрузитесь с ISO GT/OS"
    exit 2
fi
cp -f /mnt/gtos/boot/vmlinuz /mnt/gtos/usr/share/gtos/boot/vmlinuz
cp -f /mnt/gtos/boot/initrd.gz /mnt/gtos/usr/share/gtos/boot/initrd.gz
# копия на ESP для прошивок, которые ищут ядро рядом с EFI
if [ -n "$P_EFI" ] && mountpoint -q /mnt/gtos/boot/efi 2>/dev/null; then
    mkdir -p /mnt/gtos/boot/efi/EFI/gtos
    cp -f /mnt/gtos/boot/vmlinuz /mnt/gtos/boot/efi/EFI/gtos/vmlinuz 2>/dev/null || true
    cp -f /mnt/gtos/boot/initrd.gz /mnt/gtos/boot/efi/EFI/gtos/initrd.gz 2>/dev/null || true
fi

# пользователь и маркеры
mkdir -p "/mnt/gtos/home/$USER_NAME/Документы" "/mnt/gtos/home/$USER_NAME/Загрузки" \
         "/mnt/gtos/home/$USER_NAME/Изображения" "/mnt/gtos/home/$USER_NAME/Музыка" \
         "/mnt/gtos/home/$USER_NAME/Видео" "/mnt/gtos/home/$USER_NAME/Рабочий стол"
printf '%s\n' "$USER_NAME" > /mnt/gtos/var/lib/gtos/username
printf '%s\n' "$FULL_NAME" > /mnt/gtos/var/lib/gtos/fullname
printf '%s\n' "$LANG_CODE" > /mnt/gtos/var/lib/gtos/lang
printf '%s\n' "$GTOS_VER" > /mnt/gtos/var/lib/gtos/version
touch /mnt/gtos/var/lib/gtos/setup-done
touch /mnt/gtos/var/lib/gtos/installed
printf '%s\n' "GT/OS $GTOS_VER installed on $(date -u +%Y-%m-%dT%H:%M:%SZ) · boot=$BOOT_MODE" \
    > "/mnt/gtos/home/$USER_NAME/Документы/установка.txt"

# fstab
if [ -n "$P_BOOT" ]; then
    cat > /mnt/gtos/etc/fstab <<EOF
LABEL=GTOSROOT / ext4 defaults,noatime 0 1
LABEL=GTOSBOOT /boot ext4 defaults,noatime 0 2
EOF
elif [ -n "$P_EFI" ]; then
    cat > /mnt/gtos/etc/fstab <<EOF
LABEL=GTOSROOT / ext4 defaults,noatime 0 1
LABEL=GTOSEFI /boot/efi vfat umask=0077,defaults 0 2
EOF
else
    cat > /mnt/gtos/etc/fstab <<EOF
LABEL=GTOSROOT / ext4 defaults,noatime 0 1
EOF
fi

echo "GTOS_INSTALL_BOOTLOADER"
mkdir -p /mnt/gtos/boot/grub
if [ "$BOOT_MODE" = "bios" ]; then
    GRUB_INS='insmod ext2
insmod part_msdos'
else
    GRUB_INS='insmod fat
insmod part_gpt
insmod ext2'
fi

cat > /mnt/gtos/boot/grub/grub.cfg <<EOF
set timeout=5
set default=0
insmod gzio
$GRUB_INS
menuentry "GT/OS $GTOS_VER" {
    search --no-floppy --set=root --label GTOSBOOT
    if [ -f /vmlinuz ]; then
        linux /vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT
        initrd /initrd.gz
    else
        search --no-floppy --set=root --label GTOSROOT
        linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT
        initrd /boot/initrd.gz
    fi
}
menuentry "GT/OS $GTOS_VER (Safe Mode)" {
    search --no-floppy --set=root --label GTOSBOOT
    if [ -f /vmlinuz ]; then
        linux /vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT gtos.safemode=1
        initrd /initrd.gz
    else
        search --no-floppy --set=root --label GTOSROOT
        linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT gtos.safemode=1
        initrd /boot/initrd.gz
    fi
}
menuentry "GT/OS $GTOS_VER (verbose)" {
    search --no-floppy --set=root --label GTOSBOOT
    if [ -f /vmlinuz ]; then
        linux /vmlinuz console=tty0 rdinit=/init loglevel=7 root=LABEL=GTOSROOT
        initrd /initrd.gz
    else
        search --no-floppy --set=root --label GTOSROOT
        linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=7 root=LABEL=GTOSROOT
        initrd /boot/initrd.gz
    fi
}
EOF

# для GPT без отдельного GTOSBOOT — ядро на корне
if [ -z "$P_BOOT" ]; then
    cat > /mnt/gtos/boot/grub/grub.cfg <<EOF
set timeout=5
set default=0
insmod ext2
insmod gzio
insmod part_gpt
insmod fat
menuentry "GT/OS $GTOS_VER" {
    search --no-floppy --set=root --label GTOSROOT
    linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT
    initrd /boot/initrd.gz
}
menuentry "GT/OS $GTOS_VER (Safe Mode)" {
    search --no-floppy --set=root --label GTOSROOT
    linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=3 video=1920x1080 root=LABEL=GTOSROOT gtos.safemode=1
    initrd /boot/initrd.gz
}
menuentry "GT/OS $GTOS_VER (verbose)" {
    search --no-floppy --set=root --label GTOSROOT
    linux /boot/vmlinuz console=tty0 rdinit=/init loglevel=7 root=LABEL=GTOSROOT
    initrd /boot/initrd.gz
}
EOF
fi

INSTALLED_GRUB=0
INSTALLED_EFI=0

if command -v grub-install >/dev/null 2>&1; then
    if [ "$BOOT_MODE" = "bios" ] || [ "$BOOT_MODE" = "both" ] || [ "$BOOT_MODE" = "uefi" ]; then
        # legacy BIOS (на GPT нужен bios_grub раздел)
        if [ "$BOOT_MODE" = "bios" ] || [ -n "$P_BIOSGRUB" ]; then
            if grub-install --target=i386-pc --boot-directory=/mnt/gtos/boot --recheck "$DISK" >/tmp/grub-bios.log 2>&1; then
                INSTALLED_GRUB=1
                echo "GTOS_INSTALL_GRUB_BIOS_OK"
            else
                echo "GTOS_INSTALL_GRUB_BIOS_WARN"
                tail -n 20 /tmp/grub-bios.log 2>/dev/null || true
            fi
        fi
    fi
    if [ "$BOOT_MODE" = "uefi" ] || [ "$BOOT_MODE" = "both" ]; then
        if [ -n "$P_EFI" ]; then
            if grub-install --target=x86_64-efi --efi-directory=/mnt/gtos/boot/efi \
                --boot-directory=/mnt/gtos/boot --removable --recheck "$DISK" >/tmp/grub-efi.log 2>&1 \
                || grub-install --target=x86_64-efi --efi-directory=/mnt/gtos/boot/efi \
                --boot-directory=/mnt/gtos/boot --bootloader-id=GTOS --recheck "$DISK" >/tmp/grub-efi.log 2>&1; then
                INSTALLED_EFI=1
                INSTALLED_GRUB=1
                echo "GTOS_INSTALL_GRUB_EFI_OK"
                # запасной путь BOOTX64.EFI
                mkdir -p /mnt/gtos/boot/efi/EFI/BOOT
                if [ -f /mnt/gtos/boot/efi/EFI/GTOS/grubx64.efi ]; then
                    cp -f /mnt/gtos/boot/efi/EFI/GTOS/grubx64.efi /mnt/gtos/boot/efi/EFI/BOOT/BOOTX64.EFI 2>/dev/null || true
                fi
                find /mnt/gtos/boot/efi -name 'grubx64.efi' 2>/dev/null | head -n1 | while read -r g; do
                    cp -f "$g" /mnt/gtos/boot/efi/EFI/BOOT/BOOTX64.EFI 2>/dev/null || true
                done
            else
                echo "GTOS_INSTALL_GRUB_EFI_WARN"
                tail -n 30 /tmp/grub-efi.log 2>/dev/null || true
            fi
        fi
    fi
else
    echo "GTOS_INSTALL_GRUB_MISSING"
fi

cat > /mnt/gtos/var/lib/gtos/install-disk <<EOF
$DISK
${P_EFI:-$P_BOOT}
$P_ROOT
$BOOT_MODE
$INSTALLED_GRUB
$INSTALLED_EFI
$GTOS_VER
EOF

sync
umount /mnt/gtos/boot/efi 2>/dev/null || true
umount /mnt/gtos/boot 2>/dev/null || true
umount /mnt/gtos || true
echo "GTOS_INSTALL_DONE mode=$BOOT_MODE bios=$INSTALLED_GRUB efi=$INSTALLED_EFI ver=$GTOS_VER"
exit 0
