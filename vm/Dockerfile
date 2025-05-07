FROM ctfbox-vm-base:latest

ARG TEAM_ID
ENV TEAM_ID=$TEAM_ID

ARG TEAM_NAME
ENV TEAM_NAME=$TEAM_NAME

RUN mkdir -p /etc/wireguard
COPY ../router/configs/servers/server-${TEAM_ID}.conf /etc/wireguard/game.conf

# Regenerate SSH server keys
RUN rm /etc/ssh/ssh_host* && ssh-keygen -A

# Use build secrets instead of ARG for sensitive data
RUN --mount=type=secret,id=token_team_${TEAM_ID} \
    if [ -f "/run/secrets/token_team_${TEAM_ID}" ]; then \
        echo "root:$(cat /run/secrets/token_team_${TEAM_ID})" | chpasswd; \
    else \
        exit 1; \
    fi

ENTRYPOINT [ "/sbin/init", "--log-level=err" ]
