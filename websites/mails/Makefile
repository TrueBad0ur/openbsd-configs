.PHONY: all deploy update tools

all: deploy

deploy:
	doas pkg_add py3-aiohttp 2>/dev/null || true
	grep -q '^_mailsvc:' /etc/passwd || \
		doas useradd -c "mail-svc daemon" -d /var/empty -s /sbin/nologin -r 500..999 _mailsvc
	doas mkdir -p /home/scripts/mail-svc
	doas cp server.py  /home/scripts/mail-svc/server.py
	doas cp mail.py    /home/scripts/mail-svc/mail.py
	doas chown -R root:_mailsvc /home/scripts/mail-svc
	doas chmod -R 750 /home/scripts/mail-svc
	doas cp rc.d/mailsvc /etc/rc.d/mailsvc
	doas chmod +x /etc/rc.d/mailsvc
	doas rcctl disable mailsvc 2>/dev/null || true
	doas rcctl enable mailsvc
	doas rcctl stop mailsvc 2>/dev/null || true
	doas fstat -n | awk '/8081/{print $$3}' | xargs -r doas kill 2>/dev/null || true
	sleep 1
	doas rcctl start mailsvc

update:
	doas cp server.py  /home/scripts/mail-svc/server.py
	doas cp mail.py    /home/scripts/mail-svc/mail.py
	doas chown -R root:_mailsvc /home/scripts/mail-svc
	doas chmod -R 750 /home/scripts/mail-svc
	doas rcctl restart mailsvc
