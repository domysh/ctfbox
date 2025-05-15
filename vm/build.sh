apt-get update || exit 1
apt-get -y upgrade || exit 1

ln -fs /usr/share/zoneinfo/UTC /etc/localtime || exit 1

apt-get install -y \
    systemd systemd-sysv libsystemd0 ca-certificates dbus iptables \
    iproute2 kmod locales sudo udev curl openssh-server wireguard \
    iproute2 vim nano tcpdump iputils-ping python3-pip python3-venv screen \
    netcat-openbsd btop htop neovim nano curl git wget unzip zip traceroute \
    net-tools binfmt-support qemu-user-static || exit 1

curl -fsSL https://get.docker.com -o get-docker.sh || exit 1
sh get-docker.sh || exit 1
rm get-docker.sh || exit 1
apt-get update || exit 1

mkdir /var/run/sshd || exit 1
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config || exit 1
sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd || exit 1

cat > /etc/sudoers << 'EOF'
Defaults   !visiblepw
Defaults   always_set_home
Defaults   match_group_by_gid
Defaults   always_query_group_plugin
Defaults   env_reset
Defaults   env_keep =  "COLORS DISPLAY HOSTNAME HISTSIZE KDEDIR LS_COLORS"
Defaults   env_keep += "MAIL QTDIR USERNAME LANG LC_ADDRESS LC_CTYPE"
Defaults   env_keep += "LC_COLLATE LC_IDENTIFICATION LC_MEASUREMENT LC_MESSAGES"
Defaults   env_keep += "LC_MONETARY LC_NAME LC_NUMERIC LC_PAPER LC_TELEPHONE"
Defaults   env_keep += "LC_TIME LC_ALL LANGUAGE LINGUAS _XKB_CHARSET XAUTHORITY"
Defaults   secure_path = /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/var/lib/snapd/snap/bin
root	ALL=(ALL) 	ALL
%wheel ALL=(ALL) NOPASSWD: ALL
EOF

# Create init service
cat > /etc/systemd/system/init-vm.service << 'EOF'
[Unit]
Description=VM init service
[Service]
ExecStart=/usr/bin/_entry_vm_init entry
[Install]
WantedBy=multi-user.target
EOF

systemctl enable init-vm.service || exit 1

mv /entry.sh /usr/bin/_entry_vm_init || exit 1
chmod +x /usr/bin/_entry_vm_init || exit 1
rm /build.sh || exit 1
