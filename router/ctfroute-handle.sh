#!/usr/bin/env bash

echo "HELO"
read -r line
# The game server speaks this protocol over the shared unix socket. Keep the
# parsing strict: this socket is the only remote control of the game network.
read -r -a parts <<< "$line"
cmd="${parts[0]}"
arg="${parts[1]}"

case "$cmd" in
LOCK)
    ctfroute lock &> /dev/null && echo "OK" || echo "ERR"
    ;;
UNLOCK)
    ctfroute unlock &> /dev/null && echo "OK" || echo "ERR"
    ;;
FREEZE)
    ctfroute freeze &> /dev/null && echo "OK" || echo "ERR"
    ;;
BAN)
    ctfroute ban "$arg" &> /dev/null && echo "OK" || echo "ERR"
    ;;
UNBAN)
    ctfroute unban "$arg" &> /dev/null && echo "OK" || echo "ERR"
    ;;
STATUS)
    ctfroute status | tr '\n' ',' ; echo
    ;;
ENABLE-GAMESERVER-ROUTING)
    ip route add 10.10.0.1/32 via $(dig +short gameserver A | head -n 1) &> /dev/null
    echo "OK"
    ;;
*)
    echo "ERR"
    ;;
esac
