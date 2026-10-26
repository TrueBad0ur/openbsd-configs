# Notes

## CVS basics

```sh
# checkout working copy
cvs -qd anoncvs@anoncvs.eu.openbsd.org:/cvs checkout -rOPENBSD_8_0 -P src

# download raw repository (for viewvc)
rsync -avz anoncvs.eu.openbsd.org::OpenBSD-cvs/src ./cvs-src

# update working copy
cvs update

# show local changes
cvs diff -u file.c

# file history
cvs log file.c

# blame
cvs annotate file.c

# file status
cvs status
```

## ViewVC in Docker

```sh
# start
docker run --name viewvc \
  -v ./cvs-src:/opt/cvs:ro \
  -p 8002:80/tcp \
  -e VIEWVC_GID=$(stat -c%g ./cvs-src) \
  -e TZ=$(</etc/timezone) \
  --rm cmanley/viewvc

# open
http://localhost:8002/cgi-bin/viewvc.cgi

## Patches

```sh
cvs diff -u file.c > mypatch.diff
```

## Mailing lists

```
https://marc.info/?l=openbsd-tech
```
