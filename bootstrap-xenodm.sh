#!/bin/sh
set -e

echo "==> installing fonts..."
pkg_add dina-fonts

echo "==> configuring Xresources..."
cat > /etc/X11/xenodm/Xresources << 'XRES'
xlogin.Login.echoPasswd:        true
xlogin.Login.fail:              ya dun goofed
xlogin.Login.greeting:

xlogin.Login.height:            200
xlogin.Login.width:             400
xlogin.Login.y:                 320
xlogin.Login.frameWidth:        10
xlogin.Login.innerFramesWidth:  0

xlogin.Login.background:        #000000
xlogin.Login.foreground:        #eeeeee
xlogin.Login.failColor:         #b00035
xlogin.Login.inpColor:          #000000
xlogin.Login.promptColor:       #eeeeee
xlogin.Login.hiColor:           #000000
xlogin.Login.shdColor:          #000000

xlogin.Login.face:              Dina-11
xlogin.Login.failFace:          Dina-11
xlogin.Login.promptFace:        Dina-11
XRES

echo "==> configuring Xsetup_0..."
cat > /etc/X11/xenodm/Xsetup_0 << 'XSETUP'
#!/bin/sh
/usr/X11R6/bin/xsetroot -solid \#000000
/usr/X11R6/bin/xset fp+ /usr/local/share/font/dina
XSETUP
chmod +x /etc/X11/xenodm/Xsetup_0

echo "==> restarting xenodm..."
rcctl restart xenodm

echo "==> done"
