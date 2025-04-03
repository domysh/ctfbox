#!/usr/bin/bash

cd $(dirname "$(readlink -f $0)")

if [[ ! -f ".env" ]]; then
    echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
fi
