#!/bin/bash

ROUTER_IP=$(dig +short router)

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
