import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Data directory relative to backend root
DATA_DIR = Path(__file__).parent.parent / "data"
REPORTS_FILE = DATA_DIR / "reports.json"

def _ensure_file() -> None:
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not REPORTS_FILE.exists():
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def save_report(report: Dict[str, Any]) -> None:
    """Save a new call report."""
    try:
        _ensure_file()
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Insert at the beginning so newest is first
        data.insert(0, report)
        
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        logger.info("[REPORTS] Saved report for call=%s", report.get("call_id"))
    except Exception as e:
        logger.error("[REPORTS] Failed to save report: %s", e)

def get_all_reports() -> List[Dict[str, Any]]:
    """Retrieve all call reports."""
    try:
        _ensure_file()
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("[REPORTS] Failed to load reports: %s", e)
        return []
