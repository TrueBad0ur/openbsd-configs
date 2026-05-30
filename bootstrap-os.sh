#!/bin/sh
set -e

echo "==> renaming host"
echo "thinkpad" | doas tee /etc/myname
echo "==> done"
