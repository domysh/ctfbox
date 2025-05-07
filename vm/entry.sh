#!/usr/bin/env bash

###################################################
# THIS IS NOT A CHALLENGE, IS THE SETUP OF THE VM #
###################################################

if [[ "$1" == "prebuild" ]]; then
    /usr/lib/systemd/systemd-binfmt
    dockerd > /var/log/dockerd.log 2>&1 &
    while [[ ! $(docker ps 2> /dev/null) ]]; do
        sleep 1
    done
    # Only with this for loop we can exit internally from the loop
    for path in $(find /root/ -maxdepth 1 -mindepth 1 -type d); do
        if [[ -f "$path/compose.yml" || -f "$path/compose.yaml" || -f "$path/docker-compose.yml" || -f "$path/docker-compose.yaml" ]]; then
            cd $path
            echo "Building $path"
            docker compose build
            EXITCODE=$?
            echo "Build of $path exited with $EXITCODE"
            if [[ "$EXITCODE" != 0 ]]; then
                echo "Failed to build $path"
                exit $EXITCODE
            fi
        fi
    done
    echo "Prebuild execution done"
    exit 0
fi
if [[ "$1" == "entry" ]]; then

    while [[ ! $(docker ps 2> /dev/null) ]]; do
        sleep 1
    done

    find /root/ -maxdepth 1 -mindepth 1 -type d -print0 | while read -d $'\0' path
    do
        if [[ -f "$path/compose.yml" || -f "$path/compose.yaml" || -f "$path/docker-compose.yml" || -f "$path/docker-compose.yaml" ]]; then
            cd $path
            if [[ -f "$path/predeploy.sh" ]]; then
                echo "Executing predeploy.sh"
                bash predeploy.sh
            fi
            docker compose up -d --build
        fi
    done

    tail -f /dev/null
    
fi

# Pre Deploy script can be useful to run some commands before the deployment of the services
# Eg.

# #!/usr/bin/bash
# cd $(dirname "$(readlink -f $0)")
# if [[ ! -f ".env" ]]; then
#     echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
# fi

#To generate an .env file with a random SECRET_KEY different for each team