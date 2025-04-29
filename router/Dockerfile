FROM public.ecr.aws/docker/library/alpine:latest

RUN apk update && apk add iptables iproute2 bash ethtool tcpdump \
    traceroute netcat-openbsd socat iproute2-tc bind-tools python3 wireguard-tools-wg-quick

WORKDIR /app

COPY ./entry.sh ./confgen.py /app/
COPY --chown=root:root ./ctfroute.sh /usr/sbin/ctfroute
COPY ./ctfroute-handle.sh /app/ctfroute-handle.sh

RUN chmod +x /app/entry.sh
RUN chmod +x /usr/sbin/ctfroute

CMD [ "/app/entry.sh" ]
