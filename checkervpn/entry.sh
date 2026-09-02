#!/bin/bash
set -e

# Sidecar that puts a remote checker node inside the game network. The checker
# container joins this container's network namespace, so every checker sees the
# vulnboxes exactly like the control node does.

CONF=${WG_CONFIG:-/config/checker.conf}

if [ ! -f "$CONF" ]; then
    echo "Missing wireguard profile at $CONF: run 'run.py node sync <name>' first" >&2
    exit 1
fi

mkdir -p /etc/wireguard
cp "$CONF" /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf

wg-quick up wg0
echo "Checker node connected to the game network"

# Keep the namespace alive; the checker container is attached to it.
while true; do
    sleep 3600
done
