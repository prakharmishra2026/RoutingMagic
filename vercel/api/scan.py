"""POST /api/scan - Trigger a full scan of all sources."""
import json
import threading
from datetime import datetime, timezone

# Import the scan function from the main dashboard
import sys
sys.path.insert(0, '/tmp')
sys.path.insert(0, '/var/task')

try:
    from unified_scanner import scan as unified_scan
    from dashboard_adapters import scan_all
except ImportError:
    # Fallback: minimal scan
    unified_scan = None
    scan_all = None

def handler(request):
    if request.method != "POST":
        return {"error": "POST required"}, 405
    
    if unified_scan:
        # Run scan in background thread
        def bg_scan():
            unified_scan(verbose=False)
        threading.Thread(target=bg_scan, daemon=True).start()
        return {"status": "scanning", "started_at": datetime.now(timezone.utc).isoformat()}, 202
    else:
        return {"error": "Scan module not available"}, 503
