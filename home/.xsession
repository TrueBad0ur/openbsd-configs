xscreensaver -no-splash &

xinput set-prop "/dev/wsmouse" "WS Pointer Wheel Emulation" 1
xinput set-prop "/dev/wsmouse" "WS Pointer Wheel Emulation Button" 2

setxkbmap -layout us,ru -option grp:caps_switch

exec i3
