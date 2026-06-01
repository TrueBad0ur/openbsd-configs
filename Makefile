REPO != pwd

.PHONY: all packages os link system zsh xenodm firefox

all: packages os link zsh system xenodm

packages:
	doas pkg_add \
		git curl zsh htop fastfetch \
		alacritty \
		i3 i3status dmenu rofi feh \
		firefox \
		xscreensaver i3lock \
		dina-fonts \
		coreutils

os:
	echo "thinkpad" | doas tee /etc/myname
	doas ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime

link:
	mkdir -p $(HOME)/.config/i3 $(HOME)/.config/alacritty
	ln -sf $(REPO)/home/.zshrc              $(HOME)/.zshrc
	ln -sf $(REPO)/home/.xsession           $(HOME)/.xsession
	chmod +x $(REPO)/home/.xsession
	ln -sf $(REPO)/home/.xscreensaver       $(HOME)/.xscreensaver
	ln -sf $(REPO)/home/.config/i3/config          $(HOME)/.config/i3/config
	ln -sf $(REPO)/home/.config/i3/i3status.conf   $(HOME)/.config/i3/i3status.conf
	ln -sf $(REPO)/home/.config/alacritty/alacritty.toml $(HOME)/.config/alacritty/alacritty.toml

system:
	doas cp system/xenodm/Xresources /etc/X11/xenodm/Xresources
	doas cp system/xenodm/Xsetup_0   /etc/X11/xenodm/Xsetup_0
	doas chmod +x /etc/X11/xenodm/Xsetup_0

xenodm: system
	doas rcctl restart xenodm

zsh:
	[ -d $(HOME)/.oh-my-zsh ] || \
		sh -c "$$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
	[ -d $(HOME)/.oh-my-zsh/custom/plugins/zsh-autosuggestions ] || \
		git clone https://github.com/zsh-users/zsh-autosuggestions \
		$(HOME)/.oh-my-zsh/custom/plugins/zsh-autosuggestions
	grep -qF '/usr/local/bin/zsh' /etc/shells || \
		echo '/usr/local/bin/zsh' | doas tee -a /etc/shells
	[ "$$(grep "^$$(whoami):" /etc/passwd | cut -d: -f7)" = "/usr/local/bin/zsh" ] || \
		chsh -s /usr/local/bin/zsh

firefox:
	@profile=$$(ls -d $(HOME)/.mozilla/firefox/*.default-release 2>/dev/null | head -1); \
	if [ -z "$$profile" ]; then \
		echo "ERROR: firefox profile not found, run firefox once first"; exit 1; \
	fi; \
	echo "==> writing user.js to $$profile"; \
	cp home/.mozilla/firefox/user.js "$$profile/user.js"
