#!/bin/sh
set -e

echo "==> renaming host..."
echo "thinkpad" | doas tee /etc/myname
echo "==> done"

echo "==> changing timezone..."
doas ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime
echo "==> done"
