# HubSpot Signal Matcher

Automatically matches HubSpot Signals to Companies and Contacts using semantic embeddings and vector similarity search.

## What It Does

When a Signal is created in HubSpot, this system:
1. Extracts the `signal_description` and `signal_citation`
2. Generates a semantic embedding using OpenAI
3. Searches for matching Companies and/or Contacts in Supabase
4. Creates HubSpot associations for matches with ≥85% confidence

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    REAL-TIME MATCHING                      │
├─────────────────────────────────────────────────────────────┤
│  Signal Created in HubSpot                                  │
│        ↓                                                    │
│  HubSpot Workflow → Pipedream → GitHub Actions              │
│        ↓                                                    │
│  match_signal.py → OpenAI → Supabase → Create Association   │
└─────────────────────────────────────────────────────────────┘
```

## GitHub Actions Workflows

| Workflow | Schedule | What It Does |
|----------|----------|-------------|
| **Daily Sync** | 2 AM UTC | Syncs new/modified Companies & Contacts from HubSpot to Supabase vector database |
| **Process Signals** | 3 AM UTC | Finds unmatched signals and attempts to match them (backup to real-time) |
| **Webhook Signal** | On demand | Triggered by Pipedream when a new signal is created - matches in real-time |

### Manual Triggers

All workflows can be triggered manually from GitHub Actions:
- **Daily Sync**: Check "full sync" to re-embed all records
- **Process Signals**: Enter a specific signal ID, or leave blank to process all unmatched

## Services Used

| Service | Purpose |
|---------|--------|
| **HubSpot** | Source of Signals, Companies, Contacts. Associations are created here. |
| **Supabase** | PostgreSQL + pgvector for storing embeddings and similarity search |
| **OpenAI** | `text-embedding-3-small` model for generating semantic embeddings |
| **Pipedream** | Webhook relay between HubSpot and GitHub Actions |
| **GitHub Actions** | Runs all processing scripts on schedule or webhook trigger |

## How Matching Works

1. **Signal text** is built from `signal_description` + `signal_citation`
2. **Embedding** is generated via OpenAI (1536-dimensional vector)
3. **Vector search** finds similar Companies/Contacts in Supabase using cosine similarity
4. **Matches** with similarity ≥ 85% (configurable) get HubSpot associations created
5. **Match history** is logged to `match_history` table for auditing

### Signal Types

| `signal_type` | Matches To |
|---------------|------------|
| `company` | Companies only |
| `contact` | Contacts only |
| `company_contact` | Both Companies and Contacts |

## Project Structure

```
.github/workflows/
  daily-sync.yml          # Scheduled company/contact sync
  process-signals.yml     # Scheduled signal processing
  webhook-signal.yml      # Real-time webhook handler

scripts/
  daily_sync.py           # Syncs HubSpot → Supabase
  match_signal.py         # Matches a single signal
  process_all_signals.py  # Batch processes unmatched signals

lib/
  hubspot_client.py       # HubSpot API wrapper
  supabase_client.py      # Vector database operations
  embeddings.py           # OpenAI embedding generation
  matcher.py              # Core matching logic

supabase/
  schema.sql              # Database schema
```

## Supabase Tables

| Table | Purpose |
|-------|--------|
| `companies` | Company embeddings (hubspot_id, name, domain, embedding) |
| `contacts` | Contact embeddings (hubspot_id, firstname, lastname, company, embedding) |
| `match_history` | Audit log of all matching decisions |
| `sync_metadata` | Tracks last sync times |

## Configuration

| Environment Variable | Description |
|---------------------|-------------|
| `HUBSPOT_ACCESS_TOKEN` | HubSpot Private App token |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `OPENAI_API_KEY` | OpenAI API key |
| `CONFIDENCE_THRESHOLD` | Match threshold (default: 0.85) |

## Monitoring

- **GitHub Actions** → View workflow runs and logs
- **Supabase Dashboard** → Check `companies` and `contacts` row counts
- **Supabase** → Query `match_history` for matching audit trail
- **HubSpot** → Check Signal records for associations

## Cost

| Service | Cost |
|---------|------|
| Supabase | Free tier (500MB) |
| OpenAI | ~$0.01-0.10/day |
| GitHub Actions | Free (2,000 mins/month) |
| Pipedream | Free tier |
