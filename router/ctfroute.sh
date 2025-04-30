#!/bin/bash

if [[ "$1" == "lock" ]]; then
    iptables-nft -D FREEZE_HOOK -d 10.60.0.0/16 -j REJECT &> /dev/null; iptables-nft -D FORWARD -d 10.0.0.0/8 -j REJECT &> /dev/null;
    iptables-nft -A FORWARD -d 10.0.0.0/8 -j REJECT && echo "Network locked! Now players can access to their VM only!"
elif [[ "$1" == "unlock" ]]; then
    iptables-nft -D FREEZE_HOOK -d 10.60.0.0/16 -j REJECT &> /dev/null; iptables-nft -D FORWARD -d 10.0.0.0/8 -j REJECT &> /dev/null;
    echo "Network unlocked! Players can access to the whole network!"
elif [[ "$1" == "freeze" ]]; then
    iptables-nft -D FREEZE_HOOK -d 10.60.0.0/16 -j REJECT &> /dev/null; iptables-nft -D FORWARD -d 10.0.0.0/8 -j REJECT &> /dev/null;
    iptables-nft -A FREEZE_HOOK -d 10.60.0.0/16 -j REJECT
    echo "Network frozen! Players can access the game infrastructure only!"
else
    echo "Usage: $0 [lock|unlock|freeze]"
    exit 1
fi


