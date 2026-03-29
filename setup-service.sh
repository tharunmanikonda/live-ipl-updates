#!/bin/bash

# ============================================================================
# Cricket Webhook Service Setup
# ============================================================================
# Run this on the droplet to set up the service for auto-restart
# Usage: bash setup-service.sh
# ============================================================================

set -e

echo "================================================"
echo "Installing Cricket Webhook Service"
echo "================================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. Stop any running servers
echo -e "${YELLOW}1. Stopping any running servers...${NC}"
pkill -9 -f "python.*server.py" 2>/dev/null || true
sleep 2

# 2. Copy service file to systemd
echo -e "${YELLOW}2. Installing systemd service file...${NC}"
sudo cp cricket-webhook.service /etc/systemd/system/

# 3. Reload systemd daemon
echo -e "${YELLOW}3. Reloading systemd daemon...${NC}"
sudo systemctl daemon-reload

# 4. Enable service
echo -e "${YELLOW}4. Enabling service for auto-start...${NC}"
sudo systemctl enable cricket-webhook

# 5. Start service
echo -e "${YELLOW}5. Starting cricket-webhook service...${NC}"
sudo systemctl start cricket-webhook

# 6. Wait for startup
sleep 3

# 7. Check status
echo -e "${YELLOW}6. Checking service status...${NC}"
sudo systemctl status cricket-webhook

# 8. Test health endpoint
echo -e "${YELLOW}7. Testing health endpoint...${NC}"
if curl -s http://localhost:6666/health | grep -q "ok"; then
    echo -e "${GREEN}✅ Service is healthy!${NC}"
else
    echo -e "${YELLOW}⚠️  Health check pending...${NC}"
fi

echo ""
echo "================================================"
echo -e "${GREEN}✅ Service installed successfully!${NC}"
echo "================================================"
echo ""
echo "Common commands:"
echo "  View status:  sudo systemctl status cricket-webhook"
echo "  View logs:    sudo journalctl -u cricket-webhook -f"
echo "  Stop:         sudo systemctl stop cricket-webhook"
echo "  Start:        sudo systemctl start cricket-webhook"
echo "  Restart:      sudo systemctl restart cricket-webhook"
echo ""
