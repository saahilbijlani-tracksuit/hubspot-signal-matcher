#!/usr/bin/env python3
"""
Daily Sync Script - Sync modified Companies and Contacts
"""
import os
import sys
import traceback
import argparse
from datetime import datetime, timedelta

# Ensure unbuffered output for GitHub Actions
os.environ['PYTHONUNBUFFERED'] = '1'

def log(msg):
    """Print with immediate flush for GitHub Actions."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    log("="*60)
    log("HubSpot Signal Matcher - Daily Sync")
    log("="*60)
    
    parser = argparse.ArgumentParser(description="Daily sync")
    parser.add_argument("--companies-only", action="store_true")
    parser.add_argument("--contacts-only", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--hours", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    
    log(f"Arguments: full={args.full}, hours={args.hours}, batch_size={args.batch_size}")
    
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
    
    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Initialize clients with explicit error handling
    log("Initializing HubSpot client...")
    try:
        from lib.hubspot_client import HubSpotClient
        hubspot = HubSpotClient()
        log("  HubSpot client: OK")
    except Exception as e:
        log(f"  HubSpot client: FAILED")
        log(f"  Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    log("Initializing Supabase client...")
    try:
        from lib.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        log("  Supabase client: OK")
    except Exception as e:
        log(f"  Supabase client: FAILED")
        log(f"  Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    log("Initializing OpenAI embeddings client...")
    try:
        from lib.embeddings import EmbeddingGenerator
        embeddings = EmbeddingGenerator()
        log("  Embeddings client: OK")
    except Exception as e:
        log(f"  Embeddings client: FAILED")
        log(f"  Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    log("All clients initialized successfully!")
    
    # Determine sync timeframe
    since = None if args.full else (datetime.utcnow() - timedelta(hours=args.hours)).isoformat() + "Z"
    log(f"Sync mode: {'FULL (all records)' if args.full else f'Incremental (since {since})'}")
    
    companies_synced = 0
    contacts_synced = 0
    
    # Sync companies
    if not args.contacts_only:
        log("")
        log("-"*40)
        log("Starting company sync...")
        try:
            companies_synced = sync_companies(hubspot, supabase, embeddings, since=since, batch_size=args.batch_size)
            supabase.update_sync_metadata("companies", companies_synced)
            log(f"Company sync complete: {companies_synced} companies")
        except Exception as e:
            log(f"ERROR during company sync: {e}")
            traceback.print_exc()
    
    # Sync contacts
    if not args.companies_only:
        log("")
        log("-"*40)
        log("Starting contact sync...")
        try:
            contacts_synced = sync_contacts(hubspot, supabase, embeddings, since=since, batch_size=args.batch_size)
            supabase.update_sync_metadata("contacts", contacts_synced)
            log(f"Contact sync complete: {contacts_synced} contacts")
        except Exception as e:
            log(f"ERROR during contact sync: {e}")
            traceback.print_exc()
    
    log("")
    log("="*60)
    log("SYNC COMPLETE!")
    log(f"  Companies synced: {companies_synced}")
    log(f"  Contacts synced: {contacts_synced}")
    log("="*60)


def sync_companies(hubspot, supabase, embeddings, since=None, batch_size=50):
    log(f"Fetching companies (since: {since or 'all time'})...")
    processed = 0
    batch = []
    
    for company in hubspot.iter_all_companies(modified_after=since):
        text = embeddings.prepare_company_text(name=company["name"], domain=company["domain"])
        if text.strip():
            batch.append({
                "hubspot_id": company["id"],
                "name": company["name"],
                "domain": company["domain"],
                "text": text
            })
        
        if len(batch) >= batch_size:
            process_batch(batch, supabase, embeddings, "company")
            processed += len(batch)
            log(f"  Processed {processed} companies...")
            batch = []
    
    if batch:
        process_batch(batch, supabase, embeddings, "company")
        processed += len(batch)
    
    return processed


def sync_contacts(hubspot, supabase, embeddings, since=None, batch_size=50):
    log(f"Fetching contacts (since: {since or 'all time'})...")
    processed = 0
    batch = []
    
    for contact in hubspot.iter_all_contacts(modified_after=since):
        text = embeddings.prepare_contact_text(
            firstname=contact["firstname"],
            lastname=contact["lastname"],
            company=contact["company"]
        )
        if text.strip():
            batch.append({
                "hubspot_id": contact["id"],
                "firstname": contact["firstname"],
                "lastname": contact["lastname"],
                "company": contact["company"],
                "text": text
            })
        
        if len(batch) >= batch_size:
            process_batch(batch, supabase, embeddings, "contact")
            processed += len(batch)
            log(f"  Processed {processed} contacts...")
            batch = []
    
    if batch:
        process_batch(batch, supabase, embeddings, "contact")
        processed += len(batch)
    
    return processed


def process_batch(batch, supabase, embeddings, entity_type):
    texts = [item["text"] for item in batch]
    vectors = embeddings.generate_embeddings_batch(texts)
    
    if entity_type == "company":
        records = [
            {
                "hubspot_id": item["hubspot_id"],
                "name": item["name"],
                "domain": item["domain"],
                "embedding": emb,
                "embedded_text": item["text"]
            }
            for item, emb in zip(batch, vectors)
        ]
        supabase.upsert_companies_batch(records)
    else:
        records = [
            {
                "hubspot_id": item["hubspot_id"],
                "firstname": item["firstname"],
                "lastname": item["lastname"],
                "company": item["company"],
                "embedding": emb,
                "embedded_text": item["text"]
            }
            for item, emb in zip(batch, vectors)
        ]
        supabase.upsert_contacts_batch(records)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
