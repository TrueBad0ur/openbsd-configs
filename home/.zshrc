export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="dieter"
plugins=(zsh-autosuggestions)
source $ZSH/oh-my-zsh.sh

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

export CLICOLOR=1
alias ls="gls --color=auto"

fastfetch
