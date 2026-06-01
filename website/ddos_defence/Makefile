.PHONY: all deploy status flush tools

all: deploy

tools:
	doas pkg_add ttyplot fzf pcre
	mkdir -p ~/.local/bin
	curl -sL https://raw.githubusercontent.com/OpenBSDGuy/netplot/master/netplot > ~/.local/bin/netplot
	chmod +x ~/.local/bin/netplot

deploy:
	pfctl -nf pf.conf
	doas cp pf.conf /etc/pf.conf
	doas pfctl -f /etc/pf.conf

status:
	@echo "==> ddos table:"
	doas pfctl -t ddos -T show || echo "    empty"
	@echo "==> bruteforce table:"
	doas pfctl -t bruteforce -T show || echo "    empty"
	@echo "==> pf info:"
	doas pfctl -s info | head -20

flush:
	doas pfctl -t ddos -T flush
	doas pfctl -t bruteforce -T flush
	@echo "==> tables flushed"
