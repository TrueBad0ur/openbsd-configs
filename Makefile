REPO != pwd
AWG_BUILD_DIR ?= $(HOME)/repos

.PHONY: all packages os link system zsh xenodm firefox clean awg awg-script

all: packages os link zsh system xenodm

packages:
	doas pkg_add \
		git curl zsh htop fastfetch \
		alacritty \
		i3 i3status dmenu rofi feh \
		firefox \
		xscreensaver \
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
	doas mkdir -p /etc/X11/xorg.conf.d
	doas cp system/xorg.conf.d/20-trackpoint.conf /etc/X11/xorg.conf.d/20-trackpoint.conf

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

clean:
	rm -f $(HOME)/.zshrc $(HOME)/.xsession $(HOME)/.xscreensaver
	rm -f $(HOME)/.config/i3/config $(HOME)/.config/i3/i3status.conf
	rm -f $(HOME)/.config/alacritty/alacritty.toml
	rm -rf $(HOME)/.oh-my-zsh

awg:
	doas pkg_add go gmake wireguard-tools
	[ -d $(AWG_BUILD_DIR)/amneziawg-go ] || \
		git clone https://github.com/TrueBad0ur/amneziawg-go $(AWG_BUILD_DIR)/amneziawg-go
	cd $(AWG_BUILD_DIR)/amneziawg-go && gmake && doas gmake install
	[ -d $(AWG_BUILD_DIR)/amneziawg-tools ] || \
		git clone https://github.com/TrueBad0ur/amneziawg-tools $(AWG_BUILD_DIR)/amneziawg-tools
	cd $(AWG_BUILD_DIR)/amneziawg-tools/src && gmake && doas gmake install
	doas chmod 755 /etc/amnezia /etc/amnezia/amneziawg

awg-script:
	doas ln -sf $(REPO)/scripts/awg-openbsd.sh /usr/local/bin/awg-openbsd
	doas chmod +x /usr/local/bin/awg-openbsd

firefox:
	@profile=$$(ls -d $(HOME)/.mozilla/firefox/*.default-release 2>/dev/null | head -1); \
	if [ -z "$$profile" ]; then \
		echo "ERROR: firefox profile not found, run firefox once first"; exit 1; \
	fi; \
	echo "==> writing user.js to $$profile"; \
	cp home/.mozilla/firefox/user.js "$$profile/user.js"
