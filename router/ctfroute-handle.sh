#!/usr/bin/env bash

echo "HELO"
read -r line
if [[ "$line" == "LOCK" ]]; then
    ctfroute lock &> /dev/null
    echo "OK"
elif [[ "$line" == "UNLOCK" ]]; then
    ctfroute unlock &> /dev/null
    echo "OK"
elif [[ "$line" == "FREEZE" ]]; then
    ctfroute freeze &> /dev/null
    echo "OK"
elif [[ "$line" == "ENABLE-GAMESERVER-ROUTING" ]]; then
    ip route add 10.10.0.1/32 via $(dig +short gameserver)
    echo "OK"
else
    echo "ERR"
fi
