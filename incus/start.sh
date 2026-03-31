#!/usr/bin/env bash

# Use a mount namespace (not PID namespace) so:
# - Host PIDs are preserved → LXC cgroup files contain readable PIDs
# - We get a clean, private cgroup2 mount view for our setup
# - All children share our process group → SIGTERM to -PGID wipes them all
if [ -z "$CTFBOX_UNSHARED" ]; then
  exec unshare -m --kill-child \
    env CTFBOX_UNSHARED=1 "$0" "$@"
fi


# --- Cleanup via process group (no PID namespace needed) ---
PGID=$(cut -d' ' -f5 /proc/$$/stat 2>/dev/null || echo $$)
trap "cleanup; exit" SIGTERM
cleanup() {
  echo "Stopping incusd and all nested VMs..."
  VM_LIST=$(/opt/incus/bin/incus list --format=json status=RUNNING | jq -r '.[].name' 2>/dev/null || true)
  if [ -n "$VM_LIST" ]; then
    /opt/incus/bin/incus stop $VM_LIST --force || true
  fi
  /opt/incus/bin/incus admin shutdown || true
  fusermount -u /var/lib/incus-lxcfs || true
  umount -l /var/lib/incus-lxcfs 2>/dev/null || true
  # Kill our entire process group (all spawned daemons, lxcfs, udevd, etc.)
  kill -- -${PGID} 2>/dev/null || true
  echo "Cleanup done."
}

incus_run() {
  mkdir -p /var/lib/incus-lxcfs
  /opt/incus/bin/lxcfs /var/lib/incus-lxcfs --enable-loadavg --enable-cfs &
  /usr/lib/systemd/systemd-udevd &
  /opt/incus/bin/incusd &
  echo "Waiting for incus to become ready..."
  while ! incus ls >/dev/null 2>&1; do
    sleep 1
  done
  echo "incus is now ready"
}

setup_incus_cgroup_profile() {
  # Tell LXC to place all container cgroups under ${CGBASE}/vms which
  # is pre-delegated and empty. This avoids EBUSY from incusd's own cgroup.
  if [ -n "$SELF_CGROUP" ]; then
    local vms_path="${SELF_CGROUP}/vms"
    incus profile set default raw.lxc "lxc.cgroup.dir = ${vms_path}" 2>/dev/null || true
  fi
}

echo "Applying network rules..."
iptables -t mangle -N INCUS_VM_CONNECTIONS
iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.0/24 -d 10.10.100.1/32 -j RETURN
iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.1/32 -d 10.10.100.0/24 -j RETURN
iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.0/24 -d 10.10.100.0/24 -j DROP
iptables -t mangle -A PREROUTING -j INCUS_VM_CONNECTIONS
ROUTER_IP=$(dig +short router | head -n 1)
iptables -t nat -A POSTROUTING -p udp --dport 51820 -d $ROUTER_IP -j MASQUERADE
iptables -t nat -A PREROUTING -d 10.10.100.1/32 -p udp --dport 51820 -j DNAT --to-destination $ROUTER_IP:51820

if [[ ! -f /var/lib/incus/ready ]]; then
  rm -rf /var/lib/incus/*
  incus_run
  cat /incus.yml | incus admin init --preseed || exit 1
  setup_incus_cgroup_profile
  # Base VM creation now handled by Python script
  python3 customize-vm.py || exit 1
  touch /var/lib/incus/ready
  exit 0
else
  python3 customize-vm.py setup || exit 1
  incus_run
  setup_incus_cgroup_profile
  python3 customize-vm.py start || exit 1
  sleep infinity
fi
