#!/bin/sh
sleep 1
pkill -x polybar 2>/dev/null
while pgrep -x polybar > /dev/null 2>&1; do sleep 0.5; done
polybar main 2>/tmp/polybar.log &
