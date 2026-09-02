#!/bin/bash

# A checker worker node has no game network of its own to set up: it reaches the
# vulnboxes through the VPN sidecar and the control node through its address.
if [ "$CTFBOX_ROLE" = "worker" ]; then
    echo "Starting CTFBox in checker worker mode (control: $CTFBOX_CONTROL)"
    exec ./ctfserver
fi

# The router may be recreated with a different address while the game server
# keeps running, so the routes towards it are refreshed instead of being
# resolved once at boot.
sync_routes() {
    local router_ip
    router_ip=$(dig +short router A | head -n 1)
    [ -z "$router_ip" ] && return 1
    ip route replace 10.60.0.0/16 via "$router_ip" || return 1
    ip route replace 10.80.0.0/16 via "$router_ip" || return 1
    ip route replace 10.10.0.0/16 via "$router_ip" || return 1
    return 0
}

until sync_routes; do
    echo "Waiting for the router to be resolvable..."
    sleep 1
done

iptables -t nat -A POSTROUTING -d 10.10.0.0/16 -j SNAT --to-source 10.10.0.1
iptables -t nat -A POSTROUTING -d 10.60.0.0/16 -j SNAT --to-source 10.10.0.1
iptables -t nat -A POSTROUTING -d 10.80.0.0/16 -j SNAT --to-source 10.10.0.1

ip a add 10.10.0.1/32 dev eth0

echo "127.0.0.1 flagid" >> /etc/hosts

# Tell the router how to reach us straight away. This is only a fast path: the
# router agent rebuilds the same route on its own, which is what makes a router
# restart survivable without restarting the game server too.
if echo "ENABLE-GAMESERVER-ROUTING" | nc -U /unixsk/ctfroute.sock | grep -q "OK"; then
    echo "Router knows how to reach the game server"
else
    echo "Could not announce ourselves to the router, its agent will pick it up"
fi

(
    while true; do
        sleep 15
        sync_routes || echo "Cannot resolve the router, retrying"
    done
) &

./ctfserver
