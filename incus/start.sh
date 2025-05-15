#!/usr/bin/env bash

chmod +x /incus.sh

trap "cleanup; exit" SIGTERM
cleanup() {  
  CHILD_PIDS=$(pgrep -P $$)
  if [ -n "$CHILD_PIDS" ]; then
    pkill -TERM -P $$
    echo "Stopped child processes with PIDs: $CHILD_PIDS"
  else
    echo "No child processes found."
  fi
}


if [[ ! -f /var/lib/incus/ready ]]; then
  /incus.sh &
  # Wait for incus to be ready
  echo "Waiting for incus to become ready..."
  while ! incus ls >/dev/null 2>&1; do
    sleep 1
  done
  echo "incus is now ready"

  cat /incus.yml | incus admin init --preseed || exit 1
  
  # Base VM creation now handled by Python script
  python3 customize-vm.py || exit 1
  touch /var/lib/incus/ready
  exit 0;
else
  # Setup BTRFS storage before starting incus
  python3 customize-vm.py setup || exit 1
  
  echo "Applying network rules..."
  iptables -t mangle -N INCUS_VM_CONNECTIONS
  iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.0/24 -d 10.10.100.1/32 -j RETURN
  iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.1/32 -d 10.10.100.0/24 -j RETURN
  iptables -t mangle -A INCUS_VM_CONNECTIONS -s 10.10.100.0/24 -d 10.10.100.0/24 -j DROP
  iptables -t mangle -A PREROUTING -j INCUS_VM_CONNECTIONS
  # Keep the service running
  /incus.sh &
  echo "Waiting for incus to become ready..."
  while ! incus ls >/dev/null 2>&1; do
    sleep 1
  done
  echo "incus is now ready"
  python3 customize-vm.py start || exit 1
  sleep infinity
fi


