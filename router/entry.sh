#!/bin/bash

# ----- CONFIGURATION -----

PUID=${PUID:-0}
PGID=${PGID:-0}
IFS=',' read -ra TEAM_ID_ARRAY <<< "$TEAM_IDS"

#----- GAMESERVER SCOREBOARD EXPOSE -----
iptables -t nat -N SCOREBOARD_EXPOSE
iptables -t nat -A SCOREBOARD_EXPOSE -s 10.10.0.0/16 -j RETURN
iptables -t nat -A SCOREBOARD_EXPOSE -s 10.60.0.0/16 -j RETURN
iptables -t nat -A SCOREBOARD_EXPOSE -s 10.80.0.0/16 -j RETURN
iptables -t nat -A SCOREBOARD_EXPOSE -j DNAT --to-destination 10.10.0.1
iptables -t nat -A PREROUTING -p tcp --dport 80 -j SCOREBOARD_EXPOSE

#----- ANONYMIZE TRAFFIC AND BASIC RULES -----
iptables -t nat -A POSTROUTING -j MASQUERADE
iptables -t mangle -A POSTROUTING -j TTL --ttl-set 60 # Reset TTL

#Hooks chain for inserting eventually custom rules (e.g for bans)
iptables -N USER_HOOK_INIT
iptables -A FORWARD -j USER_HOOK_INIT
# Set up network rules (if network close policy will be set to DROP)
# Here are setted the always allowed connections
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Always allow connection between game infrastructure
iptables -A FORWARD -s 10.10.0.0/16 -j ACCEPT && iptables -A FORWARD -d 10.10.0.0/16 -j ACCEPT

# ADMINS TEAM IPs can always access the network
iptables -A FORWARD -s 10.80.253.0/24 -j ACCEPT

#Hooks chain for inserting eventually custom rules (e.g for bans)
iptables -N USER_HOOK_PRE_PLAYERS
iptables -A FORWARD -j USER_HOOK_PRE_PLAYERS

iptables -N FREEZE_HOOK
iptables -A FORWARD -j FREEZE_HOOK

#----- WIREGUARD PLAYER CONFIGS -----

for i in "${TEAM_ID_ARRAY[@]}" ; do
    #traffic from team to the self-VM is allowed
    iptables -A FORWARD -s 10.80.$i.0/24 -d 10.60.$i.1 -j ACCEPT
    #Allow traffic between same team members
    iptables -A FORWARD -s 10.80.$i.0/24 -d 10.80.$i.0/24 -j ACCEPT
done
# Other traffic to team members is rejected
iptables -A FORWARD -d 10.80.0.0/16 -j DROP
# Trop VPN traffic not allowed by players
iptables -A FORWARD -s 10.80.0.0/16 ! -d 10.60.0.0/16 -j DROP

#Generating wireguard configs
python3 confgen.py
# Set permissions for configs
chown -R $PUID:$PGID /app/configs
# Starting wireguard
mkdir -p /etc/wireguard
ln -s /app/configs/wg0.conf /etc/wireguard/wg0.conf
wg-quick up wg0
ip addr add 10.60.253.253/16 dev wg0
ip addr add 10.80.253.253/16 dev wg0

#----- NETWORK TRIM BANDWIDTH -----
# Define the traffic control parameters
if [[ -n "$RATE_NET" ]]; then
    # Using HTB qdisc to allocate dedicated bandwidth per network
    tc qdisc add dev wg0 root handle 1: htb default 999 r2q 100

    # Create default class for unclassified traffic
    tc class add dev wg0 parent 1: classid 1:999 htb rate 1mbit burst 50k

    # Add dedicated classes for each team network
    for i in "${TEAM_ID_ARRAY[@]}" ; do
        # Create classes for player network (10.80.x.0/24) with full bandwidth
        tc class add dev wg0 parent 1: classid 1:8$i htb rate $RATE_NET burst 100k
        tc filter add dev wg0 parent 1: protocol ip prio 1 u32 match ip dst 10.80.$i.0/24 flowid 1:8$i
        tc filter add dev wg0 parent 1: protocol ip prio 1 u32 match ip src 10.80.$i.0/24 flowid 1:8$i

        # Create classes for team VM network (10.60.x.0/24) with full bandwidth
        tc class add dev wg0 parent 1: classid 1:6$i htb rate $RATE_NET burst 100k
        tc filter add dev wg0 parent 1: protocol ip prio 1 u32 match ip dst 10.60.$i.0/24 flowid 1:6$i
        tc filter add dev wg0 parent 1: protocol ip prio 1 u32 match ip src 10.60.$i.0/24 flowid 1:6$i
    done
fi

#----- SETTING UP CTFROUTE SERVER -----
if [[ "$VM_NET_LOCKED" != "n" ]]; then
    ctfroute freeze
fi

rm -f /unixsk/ctfroute.sock
touch /running
socat UNIX-LISTEN:/unixsk/ctfroute.sock,reuseaddr,fork EXEC:"bash /app/ctfroute-handle.sh"
