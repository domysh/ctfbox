#!/bin/bash
set -e

# ROLE=box   -> the team's vulnbox, reachable at 10.60.<team>.1
# ROLE=player -> the team's players, attacking from 10.80.<team>.x
CONF=${WG_CONFIG:-/config/wg.conf}
ROLE=${ROLE:-box}

if [ ! -f "$CONF" ]; then
    echo "Missing the WireGuard profile at $CONF" >&2
    exit 1
fi

mkdir -p /etc/wireguard
cp "$CONF" /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf
wg-quick up wg0

echo "team $TEAM_ID joined the game network as $ROLE"

case "$ROLE" in
box)    exec python3 /app/service.py ;;
player) exec python3 /app/bot.py ;;
*)      echo "unknown role $ROLE" >&2; exit 1 ;;
esac
