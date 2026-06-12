.PHONY: all deploy httpd anubis relayd services mail cert ddos update clean

REPO = ${.CURDIR}
SVC_DIR = /home/scripts/website-svc

CERT_BUNDLE = /etc/ssl/0.0.0.0:443.crt
CERT_KEY    = /etc/ssl/private/0.0.0.0:443.key
CERT_SRC    = /etc/ssl/openbsd-kiku.crt
CHAIN_SRC   = /etc/ssl/openbsd-kiku-chain.crt
KEY_SRC     = /etc/ssl/private/openbsd-kiku.key
CRON_ENTRY  = 0 0 * * * acme-client openbsd-kiku && cat ${CERT_SRC} ${CHAIN_SRC} > "${CERT_BUNDLE}" && rcctl reload relayd

all: deploy

# --- Full deploy (order matters: cert before anubis/relayd) ---

deploy: httpd anubis relayd services mail
	@echo "==> websites deployed"

# --- httpd: ACME challenges + HTTP→HTTPS redirect ---

httpd:
	doas mkdir -p /var/www/htdocs /var/www/acme
	doas cp ${REPO}/mirrors/httpd.conf /etc/httpd.conf
	doas cp ${REPO}/mirrors/acme-client.conf /etc/acme-client.conf
	doas rcctl enable httpd
	doas rcctl restart httpd
	[ -f "${CERT_SRC}" ] || doas acme-client -v openbsd-kiku

# --- Anubis: PoW bot protection ---

anubis:
	pkg_info -e anubis > /dev/null 2>&1 || doas pkg_add anubis
	doas cp ${REPO}/mirrors/anubis.env /etc/anubis.env
	doas sh -c 'cat ${CERT_SRC} ${CHAIN_SRC} > "${CERT_BUNDLE}"'
	doas rm -f "${CERT_KEY}"
	doas cp ${KEY_SRC} "${CERT_KEY}"
	doas chown root:_relayd "${CERT_KEY}"
	doas chmod 640 "${CERT_KEY}"
	doas rcctl enable anubis
	doas rcctl set anubis flags ''
	doas rcctl restart anubis

# --- relayd: TLS termination ---

relayd:
	doas cp ${REPO}/mirrors/relayd.conf /etc/relayd.conf
	doas rcctl enable relayd
	doas rcctl restart relayd
	doas crontab -l 2>/dev/null | grep -qF 'rcctl reload relayd' || \
		(doas crontab -l 2>/dev/null | grep -v 'acme-client openbsd-kiku'; echo "${CRON_ENTRY}") | doas crontab -

# --- websvc: unified aiohttp service (mirrors + mails) ---

services:
	doas pkg_add py3-aiohttp 2>/dev/null || true
	grep -q '^_websvc:' /etc/passwd || \
		doas useradd -c "website service daemon" -d /var/empty -s /sbin/nologin -r 500..999 _websvc
	doas mkdir -p ${SVC_DIR}/assets ${SVC_DIR}/mirrors-assets
	doas mkdir -p /var/www/htdocs/assets
	doas cp ${REPO}/shared/server.py                    ${SVC_DIR}/server.py
	doas cp ${REPO}/mirrors/mirrors-svc/mirrors.py      ${SVC_DIR}/mirrors.py
	doas cp ${REPO}/mails/mail.py                       ${SVC_DIR}/mail.py
	doas sh -c 'cp ${REPO}/mails/assets/* ${SVC_DIR}/assets/'
	doas sh -c 'cp ${REPO}/mirrors/assets/* ${SVC_DIR}/mirrors-assets/'
	doas cp ${REPO}/root/assets/index.html              /var/www/htdocs/index.html
	doas sh -c 'cp ${REPO}/root/assets/style.css ${REPO}/root/assets/app.js /var/www/htdocs/assets/'
	doas chown -R root:_websvc ${SVC_DIR}
	doas chmod -R 750 ${SVC_DIR}
	doas cp ${REPO}/shared/rc.d/websvc /etc/rc.d/websvc
	doas chmod +x /etc/rc.d/websvc
	doas rcctl disable mirrorssvc 2>/dev/null || true
	doas rcctl stop mirrorssvc 2>/dev/null || true
	doas rcctl enable websvc
	doas rcctl stop websvc 2>/dev/null || true
	doas fstat -n | awk '/8080/{print $$3}' | xargs -r doas kill 2>/dev/null || true
	sleep 1
	doas rcctl start websvc
	@echo "==> websvc started on 127.0.0.1:8080"

# --- mail: smtpd + processor ---

MAILPROC_DIR = /home/scripts/mailproc
DB_DIR       = /var/db/mails

mail:
	grep -q '^_mailproc:' /etc/passwd || \
		doas useradd -c "mail processor daemon" -d /var/empty -s /sbin/nologin -r 500..999 _mailproc
	doas mkdir -p ${MAILPROC_DIR}
	doas cp ${REPO}/mails/processor.py ${MAILPROC_DIR}/processor.py
	doas chmod 755 ${MAILPROC_DIR}/processor.py
	doas chown root:_mailproc ${MAILPROC_DIR}
	doas chmod 750 ${MAILPROC_DIR}
	doas mkdir -p ${DB_DIR}
	doas chown _mailproc:_mailproc ${DB_DIR}
	doas chmod 755 ${DB_DIR}
	doas touch ${DB_DIR}/majordomo.log
	doas chown _mailproc ${DB_DIR}/majordomo.log
	doas cp ${REPO}/mails/smtpd.conf /etc/mail/smtpd.conf
	doas smtpd -n && doas rcctl enable smtpd && doas rcctl restart smtpd
	@echo "==> mail deployed"

# --- Cert renewal ---

cert:
	doas acme-client -v openbsd-kiku
	doas sh -c 'cat ${CERT_SRC} ${CHAIN_SRC} > "${CERT_BUNDLE}"'
	doas rcctl reload relayd

# --- DDoS defence ---

ddos:
	${MAKE} -C mirrors/ddos_defence deploy

# --- Update code only (no user creation, no cert) ---

update: services
	@echo "==> updated"

# --- Clean ---

clean:
	doas rcctl stop websvc 2>/dev/null || true
	doas rcctl disable websvc 2>/dev/null || true
	doas rm -rf ${SVC_DIR}
	doas rm -f /etc/rc.d/websvc
	@echo "==> cleaned"
