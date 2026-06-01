xscreensaver -no-splash &

xinput set-prop "/dev/wsmouse" "WS Pointer Wheel Emulation" 1
xinput set-prop "/dev/wsmouse" "WS Pointer Wheel Emulation Button" 2

setxkbmap -layout us,ru -option grp:caps_switch

while true; do
    total=$(/sbin/sysctl -n hw.physmem | /usr/bin/awk '{printf "%d", $1/1024/1024}')
    used=$(/usr/bin/vmstat | /usr/bin/awk 'NR==3{gsub("M","",$3); print int($3)}')
    echo "$(date): used=$used total=$total" >> /tmp/ram.log
    if [ -n "$used" ] && [ -n "$total" ]; then
        echo "RAM ${used}MB / ${total}MB" > /tmp/ram
    fi
    sleep 5
done &

exec i3
