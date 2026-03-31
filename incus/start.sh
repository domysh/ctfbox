#!/usr/bin/env bash

trap "cleanup; exit" SIGTERM
cleanup() {
  echo "Stopping incusd and all nested VMs..."
  # Explicitly force stop all running VMs to prevent their systemd processes from reparenting to Host PID 1
  VM_LIST=$(/opt/incus/bin/incus list --format=json status=RUNNING | jq -r '.[].name' 2>/dev/null || true)
  if [ -n "$VM_LIST" ]; then
    /opt/incus/bin/incus stop $VM_LIST --force || true
  fi
  
  /opt/incus/bin/incus admin shutdown || true
  
  echo "Stopped incusd."
  
  echo "Stopping lxcfs..."
  fusermount -u /var/lib/incus-lxcfs || true
  umount -l /var/lib/incus-lxcfs 2>/dev/null || true
  echo "Stopped lxcfs."

  CHILD_PIDS=$(pgrep -P $$)
  if [ -n "$CHILD_PIDS" ]; then
    kill -9 $CHILD_PIDS 2>/dev/null || true
    echo "Stopped child processes with PIDs: $CHILD_PIDS"
  else
    echo "No child processes found."
  fi
}

incus_run() {
    mkdir -p /var/lib/incus-lxcfs
    /opt/incus/bin/lxcfs /var/lib/incus-lxcfs --enable-loadavg --enable-cfs &
    /usr/lib/systemd/systemd-udevd &
    UDEVD_PID=$!
    /opt/incus/bin/incusd &
    echo "Waiting for incus to become ready..."
    while ! incus ls >/dev/null 2>&1; do
      sleep 1
    done
    echo "incus is now ready"
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
  # Base VM creation now handled by Python script
  python3 customize-vm.py || exit 1
  touch /var/lib/incus/ready
  exit 0;
else
  python3 customize-vm.py setup || exit 1
  # Keep the service running
  incus_run
  python3 customize-vm.py start || exit 1
  sleep infinity
fi
