#!/bin/sh
set -e

echo "==> installing packages..."
doas pkg_add zsh curl fastfetch

echo "==> installing oh-my-zsh..."
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

echo "==> writing .zshrc..."
cat > ~/.zshrc << 'ZSHRC'
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="dieter"
plugins=(git sudo)
source $ZSH/oh-my-zsh.sh

export CLICOLOR=1
alias ls="gls --color=auto"

fastfetch
ZSHRC

echo "==> setting zsh as default shell..."
chsh -s /usr/local/bin/zsh

echo "==> done"
echo "    relogin to apply"
