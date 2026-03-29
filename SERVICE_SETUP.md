# Cricket Webhook Service Setup

This guide explains how to set up the Cricket Webhook service to run automatically on your droplet with auto-restart capabilities.

## Quick Start (Recommended)

Run the setup script to install everything automatically:

```bash
cd ~/live-ipl-updates
bash setup-service.sh
```

That's it! The service will now:
- ✅ Start automatically on droplet reboot
- ✅ Automatically restart if it crashes
- ✅ Log to `/tmp/cricket_server.log`

## Manual Setup

If you prefer to set up manually:

```bash
# 1. Stop any running servers
pkill -9 -f "python.*server.py"

# 2. Copy service file
sudo cp cricket-webhook.service /etc/systemd/system/

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Enable service (auto-start on reboot)
sudo systemctl enable cricket-webhook

# 5. Start service
sudo systemctl start cricket-webhook

# 6. Check status
sudo systemctl status cricket-webhook
```

## Common Commands

### View service status
```bash
sudo systemctl status cricket-webhook
```

### View live logs
```bash
sudo journalctl -u cricket-webhook -f
```

### Stop service
```bash
sudo systemctl stop cricket-webhook
```

### Start service
```bash
sudo systemctl start cricket-webhook
```

### Restart service
```bash
sudo systemctl restart cricket-webhook
```

### View recent logs (last 50 lines)
```bash
sudo journalctl -u cricket-webhook -n 50
```

### Check if service is enabled (auto-start)
```bash
sudo systemctl is-enabled cricket-webhook
```

## Service Configuration

The service file (`cricket-webhook.service`) configures:

- **User**: Runs as root
- **Working Directory**: `/root/live-ipl-updates`
- **Environment Variables**:
  - `WEBHOOK_URL`: Poke webhook URL
  - `WEBHOOK_AUTH`: Bearer token for authentication
  - `PORT`: 6666
- **Auto-restart**: Restarts automatically if service crashes
- **Restart Delay**: 10 seconds between restart attempts
- **Logs**: Appended to `/tmp/cricket_server.log`

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
sudo journalctl -u cricket-webhook -n 100

# Verify service file syntax
systemd-analyze verify /etc/systemd/system/cricket-webhook.service

# Check if port 6666 is available
lsof -i :6666
```

### Service keeps restarting
```bash
# Check logs for the actual error
sudo journalctl -u cricket-webhook -f

# Common issues:
# 1. Port 6666 in use
# 2. Missing Python packages
# 3. File permissions
```

### View detailed service information
```bash
systemctl show cricket-webhook
```

## Benefits of Using systemd Service

✅ **Auto-start on reboot** - No manual intervention needed
✅ **Auto-restart on crash** - Service restarts automatically if it fails
✅ **Centralized logging** - View logs with `journalctl`
✅ **Clean process management** - Easy to start/stop/restart
✅ **Production-ready** - Standard Linux service management
✅ **Resource limits** - Can configure memory, CPU limits if needed
✅ **Dependency management** - Can start after other services

## Alternative: Using nohup (Simple)

If you prefer a simpler approach without systemd:

```bash
nohup bash -c 'WEBHOOK_URL="https://poke.com/api/v1/inbound/webhook" \
WEBHOOK_AUTH="Bearer ..." \
PORT=6666 python3 proxy-python/server.py' > /tmp/cricket_server.log 2>&1 &

echo $! > /tmp/cricket.pid
```

Then to stop:
```bash
kill $(cat /tmp/cricket.pid)
```

**Note**: With nohup, the service won't auto-restart if it crashes.

## Alternative: Using screen (Interactive)

If you want to keep a terminal session:

```bash
screen -S cricket
# Inside screen:
cd ~/live-ipl-updates
WEBHOOK_URL="..." WEBHOOK_AUTH="..." PORT=6666 python3 proxy-python/server.py

# Detach: Ctrl+A then D
# Reattach: screen -r cricket
```

## Monitoring

### Check if service is running
```bash
systemctl is-active cricket-webhook
```

### Monitor service usage
```bash
# View memory and CPU usage
systemctl status cricket-webhook

# Get detailed process info
ps aux | grep "[p]ython.*server.py"
```

### Set up log rotation (optional)
```bash
sudo tee /etc/logrotate.d/cricket-webhook > /dev/null << 'EOF'
/tmp/cricket_server.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 root root
}
EOF
```

## Version Information

- **Service Name**: cricket-webhook
- **Service Type**: simple
- **Auto-restart**: Yes (10s delay)
- **Logs**: `/tmp/cricket_server.log` and `journalctl`
- **Created**: 2026-03-29

## Need Help?

1. Check service status: `sudo systemctl status cricket-webhook`
2. View logs: `sudo journalctl -u cricket-webhook -f`
3. Verify config: `systemd-analyze verify /etc/systemd/system/cricket-webhook.service`
4. Check port: `lsof -i :6666`
