#!/bin/sh
set -e

echo "==> installing all packages..."
doas pkg_add \
    git \
    curl \
    zsh \
    htop \
    fastfetch \
    alacritty \
    i3 \
    i3status \
    dmenu \
    rofi \
    feh \
    firefox \
    xscreensaver \
    i3lock \
    dina-fonts \
    coreutils \
    gcc-11.2.0p19

echo "==> done"
