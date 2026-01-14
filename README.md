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
| **Daily Sync** | 2 AM UTC | Syncs new/modified Companies & Contacts from HubSpot to Supabase |
| **Process Signals** | 3 AM UTC | Finds unmatched signals and attempts to match them |
| **Webhook Signal** | On demand | Triggered when a new signal is created - matches in real-time |

All workflows can be triggered manually from the GitHub Actions tab.

## How Matching Works

1. **Signal text** is built from `signal_description` + `signal_citation`
2. **Embedding** is generated via OpenAI (1536-dimensional vector)
3. **Vector search** finds similar Companies/Contacts using cosine similarity
4. **Matches** with similarity ≥ 85% get HubSpot associations created
5. **Match history** is logged for auditing

### Signal Types

| `signal_type` | Matches To |
|---------------|------------|
| `company` | Companies only |
| `contact` | Contacts only |
| `company_contact` | Both |

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
```

## Supabase Tables

| Table | Purpose |
|-------|--------|
| `companies` | Company embeddings (name, domain) |
| `contacts` | Contact embeddings (firstname, lastname, company) |
| `match_history` | Audit log of all matching decisions |
| `sync_metadata` | Tracks last sync times |

## Monitoring

- **GitHub Actions** → View workflow runs and logs
- **Supabase Dashboard** → Check table row counts
- **HubSpot** → Check Signal records for associations
