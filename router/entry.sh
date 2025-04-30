#!/bin/bash

# ----- CONFIGURATION -----

PUID=${PUID:-0}
PGID=${PGID:-0}
DEFAULT_IFACES=$(ip route | grep default | awk '{print $5}' | sort | uniq)
IFS=',' read -ra TEAM_ID_ARRAY <<< "$TEAM_IDS"

#----- NETWORK TRIM BANDWIDTH -----
# Define the traffic control parameters
if [[ -n "$RATE_NET" ]]; then
    # Loop through all network interfaces except 'lo' and default route interfaces
    for iface in $(ip -o link show | awk -F': ' '{print $2}' | grep -Ev "^lo" | cut -d'@' -f1); do

        # Only apply tc if the interface is not part of the default routes
        if ip addr show "$iface" | grep -q "inet " && ! echo "$DEFAULT_IFACES" | grep -q "$iface"; then
            echo "Applying traffic control on interface $iface..."
            tc qdisc add dev "$iface" root tbf rate $RATE_NET burst 32kbit latency 400ms
        fi
    done
fi

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
ln -s /app/configs/wg0.conf /etc/wireguard/players.conf
wg-quick up players

#----- SETTING UP CTFROUTE SERVER -----

if [[ "$VM_NET_LOCKED" != "n" ]]; then
    ctfroute lock
fi

rm -f /unixsk/ctfroute.sock
socat UNIX-LISTEN:/unixsk/ctfroute.sock,reuseaddr,fork EXEC:"bash /app/ctfroute-handle.sh"
