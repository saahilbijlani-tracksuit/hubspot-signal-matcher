#!/usr/bin/env python3
"""Signal Matching Script

Matches a HubSpot Signal to Companies and/or Contacts
based on semantic similarity of the signal description.

Usage:
    python scripts/match_signal.py <signal_id>
    python scripts/match_signal.py <signal_id> --dry-run
    python scripts/match_signal.py <signal_id> --json
"""

import os
import sys
import json
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
    parser = argparse.ArgumentParser(
        description="Match a HubSpot Signal to Companies and Contacts"
    )
    parser.add_argument(
        "signal_id",
        help="HubSpot Signal ID to match"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Confidence threshold (default: 0.85 or CONFIDENCE_THRESHOLD env var)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without creating associations"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    log("="*50)
    log("HubSpot Signal Matcher")
    log("="*50)
    
    # Check environment variables
    log("Checking environment variables...")
    required_vars = ["HUBSPOT_ACCESS_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY"]
    
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        log(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    log("  All environment variables present")
    
    # Set threshold if provided
    if args.threshold:
        os.environ["CONFIDENCE_THRESHOLD"] = str(args.threshold)
    
    # Initialize matcher
    log("Initializing matcher...")
    try:
        from lib.matcher import SignalMatcher
        matcher = SignalMatcher()
        log("  Matcher initialized")
    except Exception as e:
        log(f"ERROR: Failed to initialize matcher: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    if args.dry_run:
        log("DRY RUN - No associations will be created")
        matcher.threshold = 0.0  # Show all potential matches
    
    # Match the signal
    log(f"Processing signal: {args.signal_id}")
    try:
        result = matcher.match_signal(args.signal_id)
    except Exception as e:
        log(f"ERROR: Failed to match signal: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        log("")
        log("="*50)
        log("RESULTS")
        log("="*50)
        log(f"Signal ID: {result['signal_id']}")
        log(f"Signal Type: {result.get('signal_type', 'unknown')}")
        log(f"Total Matches: {result['total_matches']}")
        log(f"Associations Created: {result['associations_created']}")
        
        if result.get("company_matches"):
            log("")
            log("Company Matches:")
            for match in result["company_matches"]:
                status = "CREATED" if match["association_created"] else "SKIPPED"
                log(f"  [{status}] {match['name']} ({match['similarity']:.1%})")
        
        if result.get("contact_matches"):
            log("")
            log("Contact Matches:")
            for match in result["contact_matches"]:
                status = "CREATED" if match["association_created"] else "SKIPPED"
                log(f"  [{status}] {match['name']} ({match['similarity']:.1%})")
        
        if result.get("error"):
            log(f"")
            log(f"ERROR: {result['error']}")
    
    # Exit code
    if result.get("error"):
        sys.exit(1)
    elif result["total_matches"] == 0:
        sys.exit(2)  # No matches found
    else:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
