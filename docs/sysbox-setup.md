# Sysbox Installation and Setup Guide

This guide provides instructions for installing and configuring Sysbox, which is required for running CTFBox in the recommended secure mode.

## What is Sysbox?

Sysbox is a container runtime that enables Docker containers to act more like virtual machines, allowing for enhanced isolation and security. CTFBox uses Sysbox to provide a secure environment for running team VMs.

## Installation Methods

### Debian/Ubuntu (Official Method)

This is the officially supported installation method.

1. Download the latest Sysbox release from the [official GitHub repository](https://github.com/nestybox/sysbox/releases)
2. Install the packages:
   ```bash
   # Install dependencies
   apt-get update
   apt-get install -y fuse jq wget
   
   # Update with the correct version you downloaded
   dpkg -i sysbox-ce_0.6.6-0.linux_amd64.deb
   ```

### Arch Linux (via AUR)

```bash
# Using an AUR helper like yay
yay -S sysbox

# Or manually from the AUR
git clone https://aur.archlinux.org/sysbox.git
cd sysbox
makepkg -si
```

### Fedora (via COPR)

```bash
# Enable the Karellen COPR repository
dnf copr enable karellen/karellen-sysbox

# Install sysbox
dnf install sysbox
```

## Post-Installation Configuration

### 1. Enable Sysbox Services

For systemd-based systems:
```bash
systemctl enable --now sysbox
```

Verify the service is running:
```bash
systemctl status sysbox
```

### 2. Configure Docker to Use Sysbox

Add Sysbox as a runtime in Docker's configuration:

```bash
# Create or edit the Docker daemon configuration file
mkdir -p /etc/docker
nano /etc/docker/daemon.json
```

Add the following content to the file:
```json
{
    "runtimes": {
        "sysbox-runc": {
            "path": "/usr/bin/sysbox-runc"
        }
    }
}
```

If you already have content in your `daemon.json` file, make sure to merge the configuration properly without overwriting existing settings.

### 3. Restart Docker

```bash
systemctl restart docker
```

### 4. Verify Installation

Test if Sysbox is correctly installed and configured:

```bash
docker run --runtime=sysbox-runc --rm -it nestybox/alpine-docker
```

If the container starts successfully, Sysbox is properly configured.

## Troubleshooting

### Common Issues

1. **Docker Can't Find Sysbox Runtime:**
   - Ensure the path in `daemon.json` is correct
   - Check if sysbox-runc is actually installed at that location

2. **Permission Errors:**
   - Sysbox requires specific kernel capabilities; ensure your system meets the requirements

3. **Kernel Version Incompatibility:**
   - Sysbox requires a recent Linux kernel (5.5+)
   - Check your kernel version with `uname -r`

### Getting Help

If you encounter issues with Sysbox installation:
- Check the [Sysbox documentation](https://github.com/nestybox/sysbox/tree/master/docs)
- Search for similar issues in the [Sysbox GitHub issues](https://github.com/nestybox/sysbox/issues)
- Reach out to the CTFBox community for help

## Using CTFBox without Sysbox

While not recommended for security reasons, you can run CTFBox without Sysbox using the privileged mode:

```bash
# Edit your config.json and set:
"vm-mode": "privileged"
```

**Note:** Privileged mode gives VMs access to host functionality, making container escape possible. Only use this option in trusted environments or for testing purposes.
