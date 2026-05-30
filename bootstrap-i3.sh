cat > ~/bootstrap-i3.sh << 'EOF'
#!/bin/sh
set -e

echo "==> installing packages..."
doas pkg_add rofi feh xscreensaver i3lock

echo "==> creating directories..."
mkdir -p ~/.config/i3

echo "==> writing i3 config..."
cat > ~/.config/i3/config << 'I3CONF'
set $mod Mod1

font pango:monospace 10

default_border pixel 0
default_floating_border pixel 0

floating_modifier $mod
tiling_drag modifier titlebar

bindsym $mod+Return exec xterm
bindsym $mod+Shift+q kill
bindcode $mod+40 exec --no-startup-id "rofi -modi drun -show drun"
bindsym $mod+l exec i3lock -i ~/.config/i3/background.png

bindsym $mod+Left focus left
bindsym $mod+Down focus down
bindsym $mod+Up focus up
bindsym $mod+Right focus right
bindsym $mod+j focus left
bindsym $mod+k focus down
bindsym $mod+semicolon focus right

bindsym $mod+Shift+Left move left
bindsym $mod+Shift+Down move down
bindsym $mod+Shift+Up move up
bindsym $mod+Shift+Right move right
bindsym $mod+Shift+j move left
bindsym $mod+Shift+k move down
bindsym $mod+Shift+l move up
bindsym $mod+Shift+semicolon move right

bindsym $mod+h split h
bindsym $mod+v split v
bindsym $mod+f fullscreen toggle
bindsym $mod+s layout stacking
bindsym $mod+w layout tabbed
bindsym $mod+e layout toggle split
bindsym $mod+Shift+space floating toggle
bindsym $mod+space focus mode_toggle
bindsym $mod+a focus parent

set $ws1 "1"
set $ws2 "2"
set $ws3 "3"
set $ws4 "4"
set $ws5 "5"
set $ws6 "6"
set $ws7 "7"
set $ws8 "8"
set $ws9 "9"
set $ws10 "10"

bindsym $mod+1 workspace number $ws1
bindsym $mod+2 workspace number $ws2
bindsym $mod+3 workspace number $ws3
bindsym $mod+4 workspace number $ws4
bindsym $mod+5 workspace number $ws5
bindsym $mod+6 workspace number $ws6
bindsym $mod+7 workspace number $ws7
bindsym $mod+8 workspace number $ws8
bindsym $mod+9 workspace number $ws9
bindsym $mod+0 workspace number $ws10

bindsym $mod+Shift+1 move container to workspace number $ws1
bindsym $mod+Shift+2 move container to workspace number $ws2
bindsym $mod+Shift+3 move container to workspace number $ws3
bindsym $mod+Shift+4 move container to workspace number $ws4
bindsym $mod+Shift+5 move container to workspace number $ws5
bindsym $mod+Shift+6 move container to workspace number $ws6
bindsym $mod+Shift+7 move container to workspace number $ws7
bindsym $mod+Shift+8 move container to workspace number $ws8
bindsym $mod+Shift+9 move container to workspace number $ws9
bindsym $mod+Shift+0 move container to workspace number $ws10

bindsym $mod+Shift+c reload
bindsym $mod+Shift+r restart
bindsym $mod+Shift+e exec "i3-nagbar -t warning -m 'Exit i3?' -B 'Yes' 'i3-msg exit'"

mode "resize" {
    bindsym Left resize shrink width 10 px or 10 ppt
    bindsym Right resize grow width 10 px or 10 ppt
    bindsym Up resize shrink height 10 px or 10 ppt
    bindsym Down resize grow height 10 px or 10 ppt
    bindsym Return mode "default"
    bindsym Escape mode "default"
    bindsym $mod+r mode "default"
}
bindsym $mod+r mode "resize"

bindsym XF86AudioRaiseVolume exec mixerctl -n outputs.master | awk -F, '{print ($1+5)","($2+5)}' | xargs -I{} mixerctl outputs.master={}
bindsym XF86AudioLowerVolume exec mixerctl -n outputs.master | awk -F, '{print ($1-5)","($2-5)}' | xargs -I{} mixerctl outputs.master={}

exec --no-startup-id xscreensaver -no-splash &
exec --no-startup-id feh --bg-fill ~/.config/i3/background.png

bar {
    status_command i3status --config ~/.config/i3/i3status.conf
    position top
    separator_symbol "|"
    workspace_buttons yes
    strip_workspace_numbers yes

    colors {
        background  #212121
        statusline  #DDDDDD
        separator   #777777
        focused_workspace   #777777 #2e004d #FFFFFF
        active_workspace    #212121 #212121 #FFFFFF
        inactive_workspace  #212121 #212121 #86888C
        urgent_workspace    #2F343A #e65c00 #FFFFFF
    }
}
I3CONF

echo "==> writing i3status config..."
cat > ~/.config/i3/i3status.conf << 'STATUSCONF'
general {
    colors = true
    interval = 5
    output_format = "i3bar"
}

order += "cpu_usage"
order += "disk /"
order += "wireless _first_"
order += "ethernet _first_"
order += "battery 0"
order += "memory"
order += "tztime local"

cpu_usage {
    format = "CPU %usage"
    max_threshold = 30
}

wireless _first_ {
    format_up = "WiFi %quality %essid %ip"
    format_down = ""
}

ethernet _first_ {
    format_up = "ETH %ip"
    format_down = ""
}

battery 0 {
    format = "%status %percentage %remaining"
    format_down = ""
    status_chr = "CHR"
    status_bat = "BAT"
    status_full = "FULL"
    path = "/sys/class/power_supply/BAT%d/uevent"
    low_threshold = 10
}

memory {
    format = "RAM %used"
    threshold_degraded = "25%"
}

disk "/" {
    format = "DISK %avail"
}

tztime local {
    format = "%Y-%m-%d %H:%M"
}
STATUSCONF

echo "==> copying xscreensaver config..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.xscreensaver" ]; then
    cp "$SCRIPT_DIR/.xscreensaver" ~/.xscreensaver
    echo "    .xscreensaver copied"
else
    echo "    WARNING: .xscreensaver not found next to script, skipping"
fi

echo "==> updating .xsession..."
cat > ~/.xsession << 'XSESSION'
xscreensaver -no-splash &
exec i3
XSESSION

echo "==> done"
echo "    put your wallpaper at ~/.config/i3/background.png"
echo "    then logout and login to start i3"
EOF

chmod +x ~/bootstrap-i3.sh
