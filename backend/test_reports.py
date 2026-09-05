import json
import os
import requests
from datetime import datetime, timezone
import random

# Create mock reports data
data_dir = "data"
os.makedirs(data_dir, exist_ok=True)
reports_file = os.path.join(data_dir, "reports.json")

reports = []
for i in range(3):
    confidence = random.uniform(0.1, 0.95)
    if confidence < 0.25:
        risk = "low"
    elif confidence < 0.45:
        risk = "medium"
    else:
        risk = "high"
        
    reports.append({
        "call_id": f"mock_call_{i}_{int(datetime.now().timestamp())}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(random.uniform(10, 120), 1),
        "max_confidence": float(confidence),
        "risk_level": risk,
        "recording_url": None
    })

with open(reports_file, "w") as f:
    json.dump(reports, f)

print("Mock reports created!")
