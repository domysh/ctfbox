# Use the official Debian Bookworm base image
FROM debian:stable-slim

# Set environment variables
ENV PATH="/opt/incus/bin/:${PATH}" \
    INCUS_EDK2_PATH="/opt/incus/share/qemu/" \
    LD_LIBRARY_PATH="/opt/incus/lib/" \
    INCUS_LXC_TEMPLATE_CONFIG="/opt/incus/share/lxc/config/" \
    INCUS_DOCUMENTATION="/opt/incus/doc/" \
    INCUS_LXC_HOOK="/opt/incus/share/lxc/hooks/" \
    INCUS_AGENT_PATH="/opt/incus/agent/" \
    INCUS_UI="/opt/incus/ui/"

# We make a fake systemctl so that incus doesn't error out without systemd
RUN echo "#!/bin/bash" > /sbin/systemctl && \
    echo "exit 0" >> /sbin/systemctl && \
    chmod +x /sbin/systemctl
# Install curl so we can install the keyring.
RUN echo "deb http://deb.debian.org/debian $(. /etc/os-release && echo ${VERSION_CODENAME}) contrib" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install --no-install-recommends -y curl ca-certificates && \
    mkdir -p /etc/apt/keyrings/ && \
    curl -fsSL https://pkgs.zabbly.com/key.asc -o /etc/apt/keyrings/zabbly.asc && \
    echo "deb [signed-by=/etc/apt/keyrings/zabbly.asc] https://pkgs.zabbly.com/incus/stable $(. /etc/os-release && echo ${VERSION_CODENAME}) main" > /etc/apt/sources.list.d/zabbly-incus-stable.list && \
# Install incus and so on
    apt-get update && \
    apt-get install --no-install-recommends -y fuse nftables ebtables arptables iproute2 thin-provisioning-tools openvswitch-switch btrfs-progs lvm2 udev iptables kmod  && \
    apt-get install --no-install-recommends --no-install-suggests -y zfsutils-linux && \
    apt-get install --no-install-recommends -y incus python3-pip dnsutils

COPY ./start.sh ./incus.yml ./incus.sh ./customize-vm.py /
RUN chmod +x /start.sh

CMD ["/start.sh"]
