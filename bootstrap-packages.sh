#!/bin/sh
set -e

echo "==> installing all packages..."
doas pkg_add \
    git \
    curl \
    zsh \
    neofetch \
    alacritty \
    i3 \
    i3status \
    dmenu \
    rofi \
    feh \
    xscreensaver \
    i3lock \
    dina-fonts \
    coreutils \
    gcc-11.2.0p19

echo "==> done"
