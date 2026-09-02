FROM public.ecr.aws/docker/library/alpine:latest

# One image for both halves of a simulated team: the box that runs the
# vulnerable service, and the player that attacks the other teams. Both need the
# same thing - a WireGuard tunnel into the game network - so they share it.
RUN apk add --no-cache wireguard-tools-wg-quick iproute2 iptables python3 \
    bash curl bind-tools

COPY entry.sh /entry.sh
COPY service.py bot.py /app/
RUN chmod +x /entry.sh

ENV SERVICE_PORT=8000 CONTROL_PORT=9000
CMD ["/entry.sh"]
