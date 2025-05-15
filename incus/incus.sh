#!/bin/bash
trap "cleanup; exit" SIGTERM
cleanup() {
  echo "Stopping incusd..."
  incus admin shutdown
  pkill -TERM incusd
  echo "Stopped incusd."
  echo "Stopping lxcfs..."
  pkill -TERM lxcfs
  fusermount -u /var/lib/incus-lxcfs
  echo "Stopped lxcfs."
  
  CHILD_PIDS=$(pgrep -P $$)
  if [ -n "$CHILD_PIDS" ]; then
    pkill -TERM -P $$
    echo "Stopped child processes with PIDs: $CHILD_PIDS"
  else
    echo "No child processes found."
  fi
}

mkdir -p /var/lib/incus-lxcfs

/opt/incus/bin/lxcfs /var/lib/incus-lxcfs --enable-loadavg --enable-cfs &

/usr/lib/systemd/systemd-udevd &
UDEVD_PID=$!

/opt/incus/bin/incusd &

sleep infinity