#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
nohup python3 local_server.py > server.log 2>&1 &
echo $! > server.pid
sleep 2
if ps -p $(cat server.pid) > /dev/null 2>&1; then
    echo "✓ Server started successfully (PID: $(cat server.pid))"
    echo "✓ Access at: http://localhost:5000"
    echo "✓ Logs: tail -f server.log"
    echo "✓ Stop: kill $(cat server.pid)"
else
    echo "✗ Server failed to start. Check server.log"
    cat server.log
fi
