#!/bin/bash
# Start the MA -> CarPlay streaming pipeline
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping existing processes..."
pkill -f icy_server.py 2>/dev/null || true
pkill -f "snapclient.*snapstream" 2>/dev/null || true
sleep 2

echo "Creating FIFO..."
rm -f /tmp/snapstream
mkfifo /tmp/snapstream

echo "Starting ICY server..."
nohup python3 "${SCRIPT_DIR}/icy_server.py" > /tmp/icy_server.log 2>&1 &
ICY_PID=$!
echo "  PID: ${ICY_PID}"

sleep 2

echo "Starting snapclient..."
nohup snapclient -h localhost --player file:filename=/tmp/snapstream --logsink stderr 2>/tmp/snapclient.log &
SNAP_PID=$!
echo "  PID: ${SNAP_PID}"

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "Pipeline running!"
echo "  Stream URL (LAN):      http://${LOCAL_IP}:8000/car.mp3"
echo "  Stream URL (Tailscale): http://$(tailscale ip -4 2>/dev/null || echo '<tailscale-ip>'):8000/car.mp3"
echo ""
echo "Logs:"
echo "  ICY server:  tail -f /tmp/icy_server.log"
echo "  snapclient:  tail -f /tmp/snapclient.log"
echo ""
echo "To stop: pkill -f icy_server.py; pkill -f 'snapclient.*snapstream'"