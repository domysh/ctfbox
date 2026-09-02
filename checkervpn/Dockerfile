FROM public.ecr.aws/docker/library/alpine:latest

RUN apk update && apk add --no-cache wireguard-tools-wg-quick iproute2 iptables \
    bash bind-tools netcat-openbsd

COPY ./entry.sh /entry.sh
RUN chmod +x /entry.sh

HEALTHCHECK --retries=10 --interval=3s --timeout=10s --start-period=2s \
    CMD ip link show wg0 || exit 1

CMD [ "/entry.sh" ]
