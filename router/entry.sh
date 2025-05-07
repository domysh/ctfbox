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
iptables -A FORWARD -d 10.80.0.0/16 -j REJECT
# Trop VPN traffic not allowed by players
iptables -A FORWARD -s 10.80.0.0/16 ! -d 10.60.0.0/16 -j REJECT

#Generating wireguard configs
python3 confgen.py
# Set permissions for configs
chown -R $PUID:$PGID /app/configs
# Starting wireguard
mkdir -p /etc/wireguard
ln -s /app/configs/players.conf /etc/wireguard/players.conf
ln -s /app/configs/servers.conf /etc/wireguard/servers.conf
wg-quick up players
wg-quick up servers

#----- NETWORK TRIM BANDWIDTH -----
# Define the traffic control parameters
if [[ -n "$RATE_NET" ]]; then
    # Check if the police action module is available
    # Using HTB qdisc as a simpler alternative
    tc qdisc add dev players root handle 1: htb default 10 r2q 100
    tc qdisc add dev servers root handle 1: htb default 10 r2q 100
    tc class add dev players parent 1: classid 1:1 htb rate $RATE_NET burst 100k
    tc class add dev servers parent 1: classid 1:1 htb rate $RATE_NET burst 100k
    
    # Add classes for each team
    for i in "${TEAM_ID_ARRAY[@]}" ; do
        tc class add dev players parent 1:1 classid 1:1$i htb rate $RATE_NET burst 50k
        tc class add dev servers parent 1:1 classid 1:1$i htb rate $RATE_NET burst 50k
        
        # Add filters to match traffic
        tc filter add dev players parent 1: protocol ip prio 1 u32 match ip dst 10.80.$i.0/24 flowid 1:1$i
        tc filter add dev players parent 1: protocol ip prio 1 u32 match ip src 10.80.$i.0/24 flowid 1:1$i
        tc filter add dev servers parent 1: protocol ip prio 1 u32 match ip dst 10.60.$i.0/24 flowid 1:1$i
        tc filter add dev servers parent 1: protocol ip prio 1 u32 match ip src 10.60.$i.0/24 flowid 1:1$i
    done
fi

#----- SETTING UP CTFROUTE SERVER -----

if [[ "$VM_NET_LOCKED" != "n" ]]; then
    ctfroute freeze
fi

rm -f /unixsk/ctfroute.sock
touch /running
socat UNIX-LISTEN:/unixsk/ctfroute.sock,reuseaddr,fork EXEC:"bash /app/ctfroute-handle.sh"
