#!/bin/bash

IPT=iptables-nft

usage() {
    echo "Usage: $0 [lock|unlock|freeze|ban <team_id>|unban <team_id>|status]"
}

clear_network_rules() {
    $IPT -D FREEZE_HOOK -d 10.60.0.0/16 -j DROP &> /dev/null
    $IPT -D FORWARD -d 10.0.0.0/8 -j DROP &> /dev/null
}

valid_team_id() {
    [[ "$1" =~ ^[0-9]{1,3}$ ]] && [[ "$1" -ge 0 ]] && [[ "$1" -le 255 ]]
}

case "$1" in
lock)
    clear_network_rules
    $IPT -A FORWARD -d 10.0.0.0/8 -j DROP && echo "Network locked! Now players can access to their VM only!"
    ;;
unlock)
    clear_network_rules
    echo "Network unlocked! Players can access to the whole network!"
    ;;
freeze)
    clear_network_rules
    $IPT -A FREEZE_HOOK -d 10.60.0.0/16 -j DROP
    echo "Network frozen! Players can access the game infrastructure only!"
    ;;
ban)
    if ! valid_team_id "$2"; then usage; exit 1; fi
    # A banned team is cut off the game network: its players cannot reach
    # anything, its vulnbox stays up so the other teams keep being scored.
    $IPT -C USER_HOOK_PRE_PLAYERS -s 10.80.$2.0/24 -j DROP &> /dev/null || \
        $IPT -I USER_HOOK_PRE_PLAYERS 1 -s 10.80.$2.0/24 -j DROP
    $IPT -C USER_HOOK_PRE_PLAYERS -d 10.80.$2.0/24 -j DROP &> /dev/null || \
        $IPT -I USER_HOOK_PRE_PLAYERS 1 -d 10.80.$2.0/24 -j DROP
    echo "Team $2 banned from the network!"
    ;;
unban)
    if ! valid_team_id "$2"; then usage; exit 1; fi
    $IPT -D USER_HOOK_PRE_PLAYERS -s 10.80.$2.0/24 -j DROP &> /dev/null
    $IPT -D USER_HOOK_PRE_PLAYERS -d 10.80.$2.0/24 -j DROP &> /dev/null
    echo "Team $2 unbanned!"
    ;;
status)
    if $IPT -C FREEZE_HOOK -d 10.60.0.0/16 -j DROP &> /dev/null; then
        echo "frozen"
    elif $IPT -C FORWARD -d 10.0.0.0/8 -j DROP &> /dev/null; then
        echo "locked"
    else
        echo "unlocked"
    fi
    $IPT -S USER_HOOK_PRE_PLAYERS 2> /dev/null | grep -oE '10\.80\.[0-9]+\.0/24' | grep -oE '[0-9]+\.0/24' | cut -d. -f1 | sort -u | while read -r banned; do
        echo "banned:$banned"
    done
    ;;
*)
    usage
    exit 1
    ;;
esac
