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

#----- PROTECT THE CLUSTER CONTROL PLANE -----
# The internal cluster API (checker workers, router agents, traffic ingest) must
# never be reachable from a player tunnel, even though the whole 10.10.0.0/16
# infrastructure network is otherwise allowed.
iptables -N CLUSTER_GUARD
iptables -A FORWARD -j CLUSTER_GUARD
iptables -A CLUSTER_GUARD -s 10.80.0.0/16 -p tcp --dport 8082 -j DROP
iptables -A CLUSTER_GUARD -s 10.60.0.0/16 -p tcp --dport 8082 -j DROP
iptables -A CLUSTER_GUARD -s 10.80.0.0/16 -p tcp --dport 8090 -j DROP
iptables -A CLUSTER_GUARD -s 10.60.0.0/16 -p tcp --dport 8090 -j DROP

#----- ANONYMIZE TRAFFIC AND BASIC RULES -----
# Traffic arriving from a VPN tunnel and directed at the game infrastructure
# keeps its real source address: the control room authorizes by WireGuard
# profile, so it has to see which tunnel the request came from. It is limited to
# the tunnel subnets on purpose - those are the only ones whose replies are
# routed back through this router, and anything else would break the DNAT of the
# publicly exposed scoreboard. Traffic between players and vulnboxes is still
# anonymized, so a defender cannot tell which team is attacking it.
iptables -t nat -A POSTROUTING -s 10.80.0.0/16 -d 10.10.0.0/16 -j RETURN
# Infrastructure talking to infrastructure keeps its address too: the game
# server has to tell one node's agent from another's, and they all reach it
# across the mesh. Anonymizing here would make every node look the same.
iptables -t nat -A POSTROUTING -s 10.10.0.0/16 -d 10.10.0.0/16 -j RETURN
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

#----- MESH LINK WITH THE OTHER NODES (distributed deployments only) -----
# run.py drops a wgmesh.conf in the config directory when more than one node
# takes part in the game; a single machine deployment simply has no mesh.
if [[ -f /app/configs/wgmesh.conf ]]; then
    ln -sf /app/configs/wgmesh.conf /etc/wireguard/wgmesh.conf
    wg-quick up wgmesh && echo "Mesh link with the other nodes is up"
fi

#----- SETTING UP CTFROUTE SERVER -----
if [[ "$VM_NET_LOCKED" != "n" ]]; then
    ctfroute freeze
fi

#----- ROUTER AGENT (traffic monitoring + remote control) -----
python3 /app/agent.py &

rm -f /unixsk/ctfroute.sock
touch /running
socat UNIX-LISTEN:/unixsk/ctfroute.sock,reuseaddr,fork EXEC:"bash /app/ctfroute-handle.sh"
