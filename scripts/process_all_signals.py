#!/usr/bin/env python3
"""Process All Signals Script

Finds and matches unassociated signals in HubSpot.

Usage:
    python scripts/process_all_signals.py
    python scripts/process_all_signals.py --limit 50
"""

import os
import sys
import argparse
import traceback
from datetime import datetime

# Ensure unbuffered output
os.environ['PYTHONUNBUFFERED'] = '1'

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Process all unmatched signals")
    parser.add_argument("--limit", type=int, default=100, help="Max signals to process")
    args = parser.parse_args()
    
    log("="*60)
    log("HubSpot Signal Matcher - Process All Signals")
    log("="*60)
    
    # Check environment variables
    log("Checking environment variables...")
    required = ["HUBSPOT_ACCESS_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY"]
    for var in required:
        value = os.environ.get(var, "")
        if value:
            log(f"  {var}: OK (length={len(value)})")
        else:
            log(f"  {var}: MISSING")
    
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        log(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    # Initialize clients
    log("Initializing clients...")
    try:
        from lib.hubspot_client import HubSpotClient
        from lib.matcher import SignalMatcher
        
        hubspot = HubSpotClient()
        matcher = SignalMatcher()
        log("  Clients initialized")
    except Exception as e:
        log(f"ERROR: Failed to initialize clients: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # Fetch signals
    log("")
    log("-"*40)
    log(f"Fetching signals (limit: {args.limit})...")
    
    try:
        signals = hubspot.list_signals_without_associations(limit=args.limit)
        log(f"Found {len(signals)} signals to check")
    except Exception as e:
        log(f"ERROR: Failed to fetch signals: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    if not signals:
        log("No signals found to process")
        sys.exit(0)
    
    # Process signals
    total_processed = 0
    total_matched = 0
    total_associations = 0
    errors = []
    
    log("")
    log("-"*40)
    log("Processing signals...")
    
    for i, signal in enumerate(signals):
        signal_id = signal["id"]
        signal_name = signal["properties"].get("signal_name", "Unknown")[:30]
        
        log(f"")
        log(f"[{i+1}/{len(signals)}] Signal {signal_id}: {signal_name}")
        
        try:
            result = matcher.match_signal(signal_id)
            total_processed += 1
            
            matches = result.get("total_matches", 0)
            associations = result.get("associations_created", 0)
            
            if matches > 0:
                total_matched += 1
                total_associations += associations
                log(f"  -> {matches} matches, {associations} associations created")
            else:
                log(f"  -> No matches found")
                
        except Exception as e:
            log(f"  ERROR: {e}")
            errors.append({"signal_id": signal_id, "error": str(e)})
    
    # Summary
    log("")
    log("="*60)
    log("PROCESSING COMPLETE")
    log("="*60)
    log(f"Signals processed: {total_processed}")
    log(f"Signals matched: {total_matched}")
    log(f"Associations created: {total_associations}")
    log(f"Errors: {len(errors)}")
    
    if errors:
        log("")
        log("Errors encountered:")
        for err in errors[:10]:  # Show first 10 errors
            log(f"  Signal {err['signal_id']}: {err['error']}")
        if len(errors) > 10:
            log(f"  ... and {len(errors) - 10} more")
    
    # Exit code
    if errors and total_processed == 0:
        sys.exit(1)  # All failed
    elif errors:
        sys.exit(0)  # Some succeeded
    else:
        sys.exit(0)  # All succeeded


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
