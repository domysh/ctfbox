#!/bin/bash

MY_IP=$(ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1)
PREFIX=$(echo "$MY_IP" | cut -d. -f1,2)
ROUTER_IP=$(getent ahosts router | awk '{print $1}' | grep "^$PREFIX" | head -n 1)
if [ -z "$ROUTER_IP" ]; then
    ROUTER_IP=$(getent ahosts router | awk '{print $1}' | head -n 1)
fi

ip route add 10.60.0.0/16 via $ROUTER_IP
ip route add 10.80.0.0/16 via $ROUTER_IP
ip route add 10.10.0.0/16 via $ROUTER_IP

iptables -t nat -A POSTROUTING -d 10.10.0.0/16 -j SNAT --to-source 10.10.0.1
iptables -t nat -A POSTROUTING -d 10.60.0.0/16 -j SNAT --to-source 10.10.0.1
iptables -t nat -A POSTROUTING -d 10.80.0.0/16 -j SNAT --to-source 10.10.0.1

ip a add 10.10.0.1/32 dev eth0

echo "127.0.0.1 flagid" >> /etc/hosts

echo "ENABLE-GAMESERVER-ROUTING" | nc -U /unixsk/ctfroute.sock | grep "OK" &> /dev/null || exit 1

./ctfserver
