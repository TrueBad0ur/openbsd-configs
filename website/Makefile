.PHONY: all deploy update cert ddos anubis

CERT_BUNDLE = /etc/ssl/0.0.0.0:443.crt
CERT_KEY    = /etc/ssl/private/0.0.0.0:443.key
CERT_SRC    = /etc/ssl/openbsd-kiku.crt
CHAIN_SRC   = /etc/ssl/openbsd-kiku-chain.crt
KEY_SRC     = /etc/ssl/private/openbsd-kiku.key
CRON_ENTRY  = 0 0 * * * acme-client openbsd-kiku && cat $(CERT_SRC) $(CHAIN_SRC) > "$(CERT_BUNDLE)" && rcctl reload relayd

all: deploy

deploy:
	doas mkdir -p /var/www/htdocs /var/www/acme
	doas cp acme-client.conf /etc/acme-client.conf
	doas cp index.html       /var/www/htdocs/index.html
	doas cp httpd-bootstrap.conf /etc/httpd.conf
	doas rcctl enable httpd
	doas rcctl restart httpd
	doas acme-client -v openbsd-kiku
	doas cp httpd.conf /etc/httpd.conf
	doas rcctl restart httpd
	$(MAKE) anubis
	doas crontab -l 2>/dev/null | grep -qF 'acme-client openbsd-kiku' || \
		(doas crontab -l 2>/dev/null; echo "$(CRON_ENTRY)") | doas crontab -

anubis:
	pkg_info anubis > /dev/null 2>&1 || doas pkg_add anubis
	doas cp anubis.env /etc/anubis.env
	doas cp relayd.conf /etc/relayd.conf
	doas sh -c 'cat $(CERT_SRC) $(CHAIN_SRC) > "$(CERT_BUNDLE)"'
	doas rm -f "$(CERT_KEY)"
	doas cp $(KEY_SRC) "$(CERT_KEY)"
	doas chown root:_relayd "$(CERT_KEY)"
	doas chmod 640 "$(CERT_KEY)"
	doas pkill anubis 2>/dev/null || true
	doas rcctl enable anubis relayd
	doas rcctl set anubis flags ''
	doas rcctl restart anubis
	doas rcctl restart relayd

update:
	doas cp acme-client.conf /etc/acme-client.conf
	doas cp index.html       /var/www/htdocs/index.html
	doas cp httpd.conf       /etc/httpd.conf
	doas rcctl restart httpd
	$(MAKE) anubis
	doas crontab -l 2>/dev/null | grep -qF 'acme-client openbsd-kiku' || \
		(doas crontab -l 2>/dev/null; echo "$(CRON_ENTRY)") | doas crontab -

cert:
	doas acme-client -v openbsd-kiku
	doas sh -c 'cat $(CERT_SRC) $(CHAIN_SRC) > "$(CERT_BUNDLE)"'
	doas rcctl reload relayd

ddos:
	$(MAKE) -C ddos_defence deploy
