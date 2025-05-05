#!/usr/bin/env bash


echo "HELO"
read -r line
if [[ "$line" == "LOCK" ]]; then
    ctfroute lock &> /dev/null
    echo "OK"
elif [[ "$line" == "UNLOCK" ]]; then
    ctfroute unlock &> /dev/null
    echo "OK"
elif [[ "$line" == "FREEZE" ]]; then
    ctfroute freeze &> /dev/null
    echo "OK"
else
    echo "ERR"
fi
