#!/bin/sh
set -e

echo "==> installing alacritty..."
doas pkg_add alacritty

echo "==> writing alacritty config..."
mkdir -p ~/.config/alacritty
cat > ~/.config/alacritty/alacritty.toml << 'CONF'
[window]
padding.x = 10
padding.y = 10
opacity = 0.95

[font]
size = 13.0

[font.normal]
family = "DejaVu Sans Mono"
style = "Regular"

[colors.primary]
background = "#1a1a2e"
foreground = "#e0e0e0"

[colors.normal]
black =   "#1a1a2e"
red =     "#e06c75"
green =   "#98c379"
yellow =  "#e5c07b"
blue =    "#61afef"
magenta = "#c678dd"
cyan =    "#56b6c2"
white =   "#abb2bf"

[colors.bright]
black =   "#5c6370"
red =     "#e06c75"
green =   "#98c379"
yellow =  "#e5c07b"
blue =    "#61afef"
magenta = "#c678dd"
cyan =    "#56b6c2"
white =   "#ffffff"
CONF

echo "==> updating i3 config..."
sed -i 's/exec xterm/exec alacritty/' ~/.config/i3/config

echo "==> done"
echo "    Mod+Shift+R to reload i3"
