#!/bin/sh
# Мост уведомлений: dunst → inbox для шторки GT/OS
# Запускается как script= в конфиге dunst.

export PATH=/sbin:/usr/sbin:/bin:/usr/bin
INBOX=/var/lib/gtos/notify-inbox
mkdir -p /var/lib/gtos

# dunst: appname summary body icon urgency
APP=${1:-App}
SUMMARY=${2:-Уведомление}
BODY=${3:-}
# одна строка: epoch|app|title|body
SAFE_APP=$(printf '%s' "$APP" | tr '|\n\r' '   ' | cut -c1-40)
SAFE_SUM=$(printf '%s' "$SUMMARY" | tr '|\n\r' '   ' | cut -c1-80)
SAFE_BODY=$(printf '%s' "$BODY" | tr '|\n\r' '   ' | cut -c1-160)
TS=$(date +%s)
printf '%s|%s|%s|%s\n' "$TS" "$SAFE_APP" "$SAFE_SUM" "$SAFE_BODY" >> "$INBOX"
# не раздувать
if [ -f "$INBOX" ]; then
    tail -n 40 "$INBOX" > "$INBOX.tmp" 2>/dev/null && mv -f "$INBOX.tmp" "$INBOX"
fi
exit 0
