.PHONY: all deploy cert ddos

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
	doas crontab -l 2>/dev/null | grep -qF 'acme-client openbsd-kiku' || \
		(doas crontab -l 2>/dev/null; echo "0 0 * * * acme-client openbsd-kiku && rcctl reload httpd") | doas crontab -

cert:
	doas acme-client -v openbsd-kiku
	doas rcctl reload httpd

ddos:
	$(MAKE) -C ddos_defence deploy
