#!/bin/sh
# AmneziaWG userspace client for OpenBSD
# Requires: amneziawg-go, awg (amneziawg-tools), python3
# Usage: awg-openbsd.sh --config <config> {start|stop|status|restart}
#
# Example: awg-openbsd.sh --config /etc/amnezia/amneziawg/amster.conf start

set -e

usage() {
    echo "Usage: $(basename $0) --config <config> {start|stop|status|restart}"
    exit 1
}

CONF=""
CMD=""

while [ $# -gt 0 ]; do
    case "$1" in
        --config) CONF="$2"; shift 2 ;;
        start|stop|status|restart) CMD="$1"; shift ;;
        *) usage ;;
    esac
done

[ -n "$CONF" ] || usage
[ -n "$CMD" ] || usage

[ "$(id -u)" -eq 0 ] || exec doas "$0" --config "$CONF" "$CMD"

AWG_CONF="/tmp/awg-openbsd-$(basename $CONF .conf).conf"
INTERFACE=""
GW="$(netstat -nr | awk '/^default/{print $2; exit}')"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

get_tun_interface() {
    local index=0
    while ifconfig tun$index > /dev/null 2>&1; do
        index=$((index + 1))
    done
    INTERFACE="tun$index"
}

parse_conf() {
    LOCAL_IP=$(grep -i "^[[:space:]]*Address[[:space:]]*=" $CONF | head -1 | sed 's/.*=[[:space:]]*//' | tr -d ' ' | cut -d'/' -f1)
    MTU=$(grep -i "^[[:space:]]*MTU[[:space:]]*=" $CONF | head -1 | sed 's/.*=[[:space:]]*//' | tr -d ' ')
    MTU="${MTU:-1420}"

    ENDPOINT=$(grep -i "^[[:space:]]*Endpoint[[:space:]]*=" $CONF | head -1 | sed 's/.*=[[:space:]]*//' | tr -d ' ')
    SERVER_HOST=$(echo $ENDPOINT | sed 's/:.*//')
    SERVER_PORT=$(echo $ENDPOINT | sed 's/.*://')

    SERVER_IP=$(host $SERVER_HOST 2>/dev/null | awk '/has address/{print $4; exit}')
    [ -n "$SERVER_IP" ] || SERVER_IP="$SERVER_HOST"
}

prepare_conf() {
    rm -f "$AWG_CONF"
    python3 -c "
skip = {'address','dns','mtu','table','preup','postup','predown','postdown','saveconfig'}
with open('$CONF') as f:
    for line in f:
        key = line.split('=')[0].strip().lower()
        if key not in skip:
            print(line, end='')
" > $AWG_CONF
}

get_peer_ip() {
    SUBNET=$(echo $LOCAL_IP | sed 's/\.[0-9]*$//')
    PEER_IP="${SUBNET}.1"
}

wait_for_handshake() {
    local retries=3
    local i=0
    while [ $i -lt $retries ]; do
        sleep 1
        hs=$(awg show $INTERFACE latest-handshakes 2>/dev/null | awk '{print $2}')
        if [ -n "$hs" ] && [ "$hs" != "0" ]; then
            echo "    handshake: ok"
            return 0
        fi
        i=$((i + 1))
        echo "    waiting... ($i/$retries)"
    done
    echo "    WARNING: no handshake yet, tunnel may not be working"
}

cmd_start() {
    echo "==> checking dependencies..."
    which amneziawg-go > /dev/null || die "amneziawg-go not found in PATH"
    which awg > /dev/null || die "awg not found in PATH"
    [ -f "$CONF" ] || die "config not found: $CONF"

    echo "==> parsing config..."
    parse_conf
    get_tun_interface

    echo "    interface:  $INTERFACE"
    echo "    local ip:   $LOCAL_IP"
    echo "    server:     $SERVER_HOST ($SERVER_IP:$SERVER_PORT)"
    echo "    gateway:    $GW"
    echo "    mtu:        $MTU"

    echo "==> cleaning up existing state..."
    kill $(pgrep amneziawg-go) 2>/dev/null || true
    sleep 1

    echo "==> preparing stripped config..."
    prepare_conf
    get_peer_ip

    echo "==> starting amneziawg-go..."
    WG_PROCESS_FOREGROUND=1 amneziawg-go $INTERFACE &
    sleep 3

    echo "==> applying amneziawg config..."
    awg setconf $INTERFACE $AWG_CONF

    echo "==> configuring interface..."
    ifconfig $INTERFACE inet $LOCAL_IP $PEER_IP netmask 255.255.255.255
    ifconfig $INTERFACE mtu $MTU
    ifconfig $INTERFACE up

    echo "==> adding routes..."
    route add -host $SERVER_IP -gateway $GW
    route add -inet 0.0.0.0/1 $PEER_IP
    route add -inet 128.0.0.0/1 $PEER_IP

    echo "==> waiting for handshake..."
    wait_for_handshake

    echo "==> done"
}

cmd_stop() {
    parse_conf 2>/dev/null || true

    echo "==> stopping amneziawg-go..."
    kill $(pgrep amneziawg-go) 2>/dev/null || true
    sleep 1

    echo "==> removing routes..."
    route delete -host $SERVER_IP 2>/dev/null || true
    route delete -inet 0.0.0.0/1 2>/dev/null || true
    route delete -inet 128.0.0.0/1 2>/dev/null || true

    echo "==> destroying tun interfaces..."
    for i in $(ifconfig | grep "^tun" | cut -d: -f1); do
        ifconfig $i destroy 2>/dev/null || true
    done

    echo "==> done"
}

cmd_status() {
    parse_conf 2>/dev/null || true

    echo "==> process:"
    pgrep -l amneziawg-go || echo "    not running"

    echo "==> tun interfaces:"
    ifconfig | grep "^tun" || echo "    none"

    echo "==> handshake:"
    for i in $(ifconfig | grep "^tun" | cut -d: -f1); do
        echo "    $i: $(awg show $i latest-handshakes 2>/dev/null || echo 'no data')"
    done

    echo "==> routes:"
    netstat -nr | grep -E "0/1|tun" || echo "    no vpn routes"
}

case "$CMD" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
esac
