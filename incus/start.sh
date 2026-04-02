#!/usr/bin/env bash

LXCFS_PID=""
UDEVD_PID=""
INCUSD_PID=""
VM_LIST=""

# SIGWINCH is used due to podman usually kills the incusd process before allowing us to properly shut it down
# It's used to catch the signal avoiding to kill the daemons by podman but to trigger the cleanup function only

cleanup() {
  trap - SIGWINCH SIGTERM SIGINT EXIT

  # Redirect ALL output from this function to the log file (debug)
  # exec >> /vmdata/cleanup_debug.log 2>&1

  echo "----------------------------------------"
  echo "$(date): CLEANUP TRIGGERED"

  # 1. Gracefully stop all running VMs
  echo "Checking for running VMs..."
  VM_LIST=$(/opt/incus/bin/incus list --format=json status=RUNNING | jq -r '.[].name' 2>/dev/null || true)
  if [ -n "$VM_LIST" ]; then
    echo "Stopping VMs: $VM_LIST"
    /opt/incus/bin/incus stop $VM_LIST --force || true
  else
    echo "No running VMs found."
  fi

  # 2. Graceful Incus shutdown
  echo "Initiating Incus admin shutdown..."
  /opt/incus/bin/incus admin shutdown 2>/dev/null || true

  # 3. Send termination signals
  echo "Sending SIGTERM to daemons..."
  [ -n "$INCUSD_PID" ] && kill -TERM "$INCUSD_PID" 2>/dev/null
  [ -n "$LXCFS_PID" ] && kill -TERM "$LXCFS_PID" 2>/dev/null
  [ -n "$UDEVD_PID" ] && kill -TERM "$UDEVD_PID" 2>/dev/null

  # 4. THE MAGIC BULLET: Wait for them to actually die
  echo "Waiting for daemons to finish shutting down..."
  [ -n "$INCUSD_PID" ] && wait "$INCUSD_PID" 2>/dev/null
  [ -n "$LXCFS_PID" ] && wait "$LXCFS_PID" 2>/dev/null
  [ -n "$UDEVD_PID" ] && wait "$UDEVD_PID" 2>/dev/null
  echo "Daemons have successfully exited."

  # 5. Cleanup mounts
  echo "Cleaning up mounts..."
  fusermount -u /var/lib/incus-lxcfs 2>/dev/null || true
  umount -l /var/lib/incus-lxcfs 2>/dev/null || true

  echo "$(date): CLEANUP COMPLETE"
  exit 0
}
# Ensure signals trigger cleanup
trap cleanup SIGWINCH SIGTERM SIGINT EXIT

incus_run() {
  echo "Starting daemons..."
  mkdir -p /var/lib/incus-lxcfs
  /opt/incus/bin/lxcfs /var/lib/incus-lxcfs --enable-loadavg --enable-cfs &
  LXCFS_PID=$!
  /usr/lib/systemd/systemd-udevd &
  UDEVD_PID=$!
  /opt/incus/bin/incusd &
  INCUSD_PID=$!

  echo "Waiting for incus to become ready..."
  while ! incus ls >/dev/null 2>&1; do
    sleep 1
  done
  echo "incus is now ready"
}

# Ensure IP forwarding is enabled for the bridge
sysctl -w net.ipv4.ip_forward=1 2>/dev/null || true

echo "Applying network rules..."
iptables -t mangle -N INCUS_VM_CONNECTIONS
iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.0/24 -d 10.10.100.1/32 -j RETURN
iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.1/32 -d 10.10.100.0/24 -j RETURN
# Intra-subnet isolation rule removed to allow VM-to-VM connectivity
iptables -t mangle -A PREROUTING -j INCUS_VM_CONNECTIONS

# Resolve router IP once with fallback
ROUTER_IP=$(dig +short router | head -n 1)
if [ -n "$ROUTER_IP" ]; then
  iptables -t nat -A POSTROUTING -p udp --dport 51820 -d $ROUTER_IP -j MASQUERADE
  iptables -t nat -A PREROUTING -d 10.10.100.1/32 -p udp --dport 51820 -j DNAT --to-destination ${ROUTER_IP}:51820
else
  echo "[WARNING] Could not resolve 'router' IP, skip some NAT rules"
fi

if [[ ! -f /var/lib/incus/ready ]]; then
  rm -rf /var/lib/incus/*
  incus_run
  cat /incus.yml | incus admin init --preseed || exit 1
  # Base VM creation now handled by Python script
  python3 customize-vm.py || exit 1
  touch /var/lib/incus/ready
  exit 0
else
  python3 customize-vm.py setup || exit 1
  incus_run
  python3 customize-vm.py start || exit 1
  sleep infinity & wait $!
fi