#!/usr/bin/env bash

chmod +x /incus.sh

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
  # Start incus daemon in background
  /incus.sh &
  
  # Wait for incus to be ready
  echo "Waiting for incus to become ready on restart..."
  while ! incus ls >/dev/null 2>&1; do
    sleep 1
  done
  echo "incus is now ready"

  # Start all existing VMs
  echo "Starting all VMs..."
  VM_LIST=$(incus list -f csv | grep "^vm" | cut -d',' -f1)
  
  for vm in $VM_LIST; do
    echo "Starting VM: $vm"
    incus start $vm || echo "Failed to start $vm"
  done
  
  # Apply network rules
  echo "Applying network rules..."
  iptables -t nat -s 10.10.100.0/24 -d 10.10.100.0/24 -A PREROUTING -j DROP
  
  # Keep the service running
  exec /incus.sh
fi


