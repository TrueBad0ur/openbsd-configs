REPO != pwd
AWG_BUILD_DIR ?= $(HOME)/repos

.PHONY: all packages os system zsh xenodm firefox clean awg awg-script claude websites ddos \
        link link-rice link-minimal rice

# default: minimal (no picom/polybar)
all: packages os zsh link-minimal system

packages:
	doas pkg_add \
		git curl zsh htop fastfetch \
		alacritty \
		i3 i3status dmenu rofi feh \
		firefox \
		xscreensaver \
		dina-fonts \
		coreutils \
		scrot \
		xclip \
		node

# --- Profiles ---

link: link-minimal

link-minimal:
	@echo "==> profile: minimal"
	mkdir -p $(HOME)/.config/i3 $(HOME)/.config/alacritty $(HOME)/.config/rofi
	ln -sf $(REPO)/home/.zshrc                              $(HOME)/.zshrc
	ln -sf $(REPO)/home/.xsession                           $(HOME)/.xsession
	chmod +x $(REPO)/home/.xsession
	ln -sf $(REPO)/home/.xscreensaver                       $(HOME)/.xscreensaver
	ln -sf $(REPO)/home/.config/i3/config.minimal           $(HOME)/.config/i3/config
	ln -sf $(REPO)/home/.config/i3/i3status.conf            $(HOME)/.config/i3/i3status.conf
	ln -sf $(REPO)/home/.config/alacritty/alacritty.toml    $(HOME)/.config/alacritty/alacritty.toml
	rm -f $(HOME)/.config/rofi/config.rasi
	pkill -x polybar 2>/dev/null || true
	pkill -x picom   2>/dev/null || true
	pkill -x dunst   2>/dev/null || true
	@echo "==> done. restart i3: Mod+Shift+r"

link-rice:
	@echo "==> profile: rice (picom + polybar + dunst)"
	doas pkg_add picom polybar dunst 2>/dev/null || true
	mkdir -p $(HOME)/.config/i3 $(HOME)/.config/alacritty \
		$(HOME)/.config/picom $(HOME)/.config/polybar \
		$(HOME)/.config/dunst $(HOME)/.config/rofi
	ln -sf $(REPO)/home/.zshrc                              $(HOME)/.zshrc
	ln -sf $(REPO)/home/.xsession                           $(HOME)/.xsession
	chmod +x $(REPO)/home/.xsession
	ln -sf $(REPO)/home/.xscreensaver                       $(HOME)/.xscreensaver
	ln -sf $(REPO)/home/.config/i3/config                   $(HOME)/.config/i3/config
	ln -sf $(REPO)/home/.config/i3/i3status.conf            $(HOME)/.config/i3/i3status.conf
	ln -sf $(REPO)/home/.config/alacritty/alacritty.toml    $(HOME)/.config/alacritty/alacritty.toml
	ln -sf $(REPO)/home/.config/picom/picom.conf            $(HOME)/.config/picom/picom.conf
	ln -sf $(REPO)/home/.config/polybar/config.ini          $(HOME)/.config/polybar/config.ini
	ln -sf $(REPO)/home/.config/polybar/launch.sh           $(HOME)/.config/polybar/launch.sh
	chmod +x $(REPO)/home/.config/polybar/launch.sh
	ln -sf $(REPO)/home/.config/dunst/dunstrc               $(HOME)/.config/dunst/dunstrc
	ln -sf $(REPO)/home/.config/rofi/config.rasi            $(HOME)/.config/rofi/config.rasi
	@echo "==> done. restart i3: Mod+Shift+r"

rice: link-rice

# --- System ---

os:
	echo "thinkpad" | doas tee /etc/myname
	doas ln -fs /usr/share/zoneinfo/Europe/Moscow /etc/localtime

system:
	doas ln -sf $(REPO)/system/xenodm/Xresources /etc/X11/xenodm/Xresources
	doas ln -sf $(REPO)/system/xenodm/Xsetup_0   /etc/X11/xenodm/Xsetup_0
	doas chmod +x $(REPO)/system/xenodm/Xsetup_0

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
	rm -f $(HOME)/.config/picom/picom.conf
	rm -f $(HOME)/.config/polybar/config.ini $(HOME)/.config/polybar/launch.sh
	rm -f $(HOME)/.config/dunst/dunstrc
	rm -f $(HOME)/.config/rofi/config.rasi
	rm -rf $(HOME)/.oh-my-zsh

# --- VPN ---

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

# --- Misc ---

claude:
	doas npm install -g @anthropic-ai/claude-code@2.1.112 --ignore-scripts

websites:
	$(MAKE) -C websites deploy

ddos:
	$(MAKE) -C websites ddos

firefox:
	@profile=$$(ls -d $(HOME)/.mozilla/firefox/*.default-release 2>/dev/null | head -1); \
	if [ -z "$$profile" ]; then \
		echo "ERROR: firefox profile not found, run firefox once first"; exit 1; \
	fi; \
	echo "==> writing user.js to $$profile"; \
	cp home/.mozilla/firefox/user.js "$$profile/user.js"
