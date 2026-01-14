# HubSpot Signal to Company/Contact Matching Agent

An intelligent agent that automatically matches HubSpot Signals to the most appropriate Companies and Contacts using semantic embeddings and vector similarity search.

## 🎯 What It Does

When a new Signal is created in HubSpot:
1. Extracts `signal_description` and `signal_citation` from the signal
2. Generates a semantic embedding using OpenAI
3. Searches for matching Companies (by `name` + `domain`) and Contacts (by `firstname` + `lastname` + `company`)
4. Creates HubSpot associations for all matches with ≥85% confidence
5. Handles `company`, `contact`, and `company_contact` signal types

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        REAL-TIME FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│  HubSpot Signal Created                                         │
│          ↓                                                      │
│  HubSpot Workflow (triggers on signal creation)                 │
│          ↓                                                      │
│  Pipedream (webhook relay)                                      │
│          ↓                                                      │
│  GitHub Actions (repository_dispatch)                           │
│          ↓                                                      │
│  Python Script → OpenAI → Supabase → HubSpot Association        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SCHEDULED JOBS                             │
├─────────────────────────────────────────────────────────────────┤
│  Daily Sync (2 AM UTC)                                          │
│    → Syncs new/modified Companies & Contacts to Supabase        │
│                                                                 │
│  Process Signals (3 AM UTC)                                     │
│    → Processes any unmatched signals (backup to real-time)      │
└─────────────────────────────────────────────────────────────────┘
```

## 📋 Prerequisites

- **HubSpot** account with API access (Private App)
- **Supabase** account (free tier works)
- **OpenAI** API key
- **GitHub** repository (for Actions)
- **Pipedream** account (free tier works - for webhook relay)

## 🚀 Setup Instructions

### Step 1: Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Once created, go to **SQL Editor** and run the schema from `supabase/schema.sql`
3. Go to **Settings → API** and note down:
   - **Project URL** (e.g., `https://xxxxx.supabase.co`)
   - **Service Role Key** (starts with `eyJ...` - use this one, NOT the anon key)

### Step 2: Create HubSpot Private App

1. Go to HubSpot → Settings → Integrations → Private Apps
2. Create a new app with these scopes:
   - `crm.objects.companies.read`
   - `crm.objects.contacts.read`
   - `crm.objects.custom.read`
   - `crm.objects.custom.write`
   - `crm.schemas.custom.read`
3. Copy the **Access Token**

### Step 3: Configure GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Value |
|-------------|-------|
| `HUBSPOT_ACCESS_TOKEN` | Your HubSpot Private App token |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase **service role** key |
| `OPENAI_API_KEY` | Your OpenAI API key |

### Step 4: Create GitHub Personal Access Token

For Pipedream to trigger GitHub Actions:

1. Go to GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
2. Generate new token with:
   - Repository access: Select this repository
   - Permissions: Contents (Read and write)
3. Copy the token for Step 6

### Step 5: Run Initial Embedding Sync

Embed all existing Companies (and optionally Contacts) into Supabase:

1. Go to **GitHub Actions** → **Daily Sync** workflow
2. Click **Run workflow**
3. ✅ Check **"Run full sync (ignore last sync time)"**
4. Click **Run workflow**

This may take 30-60 minutes for ~100K companies.

### Step 6: Set Up Pipedream Webhook Relay

Since HubSpot can't directly call GitHub's `repository_dispatch` API, we use Pipedream as a relay:

1. Go to [pipedream.com](https://pipedream.com) and create an account
2. Create a new **Workflow**
3. **Trigger**: Select **HTTP / Webhook** → **HTTP Requests**
4. Copy the webhook URL (e.g., `https://xxxxx.m.pipedream.net`)
5. **Add Step**: Select **HTTP** → **Send any HTTP Request**
6. Configure:
   - **Method**: `POST`
   - **URL**: `https://api.github.com/repos/YOUR_USERNAME/hubspot-signal-matcher/dispatches`
   - **Headers**:
     - `Authorization`: `Bearer YOUR_GITHUB_PAT`
     - `Accept`: `application/vnd.github+json`
   - **Body**:
     ```json
     {
       "event_type": "process-signal",
       "client_payload": {
         "signal_id": "{{steps.trigger.event.body.signal_id}}"
       }
     }
     ```
7. **Deploy** the workflow

### Step 7: Create HubSpot Workflow

1. Go to HubSpot → Automation → Workflows
2. Create a new **Custom Object-based** workflow
3. **Trigger**: Signal is created
4. **Action**: Send webhook
   - URL: Your Pipedream webhook URL
   - Method: POST
   - Body:
     ```json
     {
       "signal_id": "{{signal_id}}"
     }
     ```
5. Turn on the workflow

## 📁 Project Structure

```
├── .github/workflows/
│   ├── daily-sync.yml        # Daily sync of Companies/Contacts (2 AM UTC)
│   ├── process-signals.yml   # Process unmatched signals (3 AM UTC + manual)
│   └── webhook-signal.yml    # Real-time signal processing via webhook
├── scripts/
│   ├── daily_sync.py         # Incremental sync script
│   ├── match_signal.py       # Single signal matching
│   ├── process_all_signals.py # Batch process unmatched signals
│   └── initial_setup.py      # One-time bulk embedding (optional)
├── lib/
│   ├── hubspot_client.py     # HubSpot API wrapper
│   ├── supabase_client.py    # Vector DB operations
│   ├── embeddings.py         # OpenAI embeddings
│   └── matcher.py            # Matching algorithm
├── supabase/
│   └── schema.sql            # Database schema
└── docs/
    ├── ARCHITECTURE.md       # Technical architecture details
    └── HUBSPOT_WORKFLOW_SETUP.md  # Detailed HubSpot setup guide
```

## 🔧 Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HUBSPOT_ACCESS_TOKEN` | HubSpot Private App token | Required |
| `SUPABASE_URL` | Supabase project URL | Required |
| `SUPABASE_KEY` | Supabase service role key | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `CONFIDENCE_THRESHOLD` | Match threshold (0.0-1.0) | `0.85` |

## 📊 GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|-------|
| **Daily Sync** | 2 AM UTC daily + manual | Sync new/modified Companies & Contacts |
| **Process Signals** | 3 AM UTC daily + manual | Process unmatched signals |
| **Webhook Signal** | Pipedream webhook | Real-time signal matching |

### Manual Triggers

- **Daily Sync**: Run with "full sync" checkbox to re-embed everything
- **Process Signals**: Run with a specific signal ID, or process all unmatched

## 💰 Cost Estimate

| Service | Cost |
|---------|------|
| **Supabase** | Free tier (500MB) or $25/mo |
| **OpenAI Embeddings** | ~$2-5 initial setup, ~$0.01-0.10/day |
| **GitHub Actions** | Free (2,000 mins/month) |
| **Pipedream** | Free tier (100 invocations/day) |

## 🐛 Troubleshooting

### Webhook not triggering
- Verify Pipedream workflow is **deployed** (not draft)
- Check HubSpot workflow is **turned on**
- Verify GitHub PAT has correct permissions
- Check Pipedream logs for errors

### No matches found
- Verify companies are in Supabase: `SELECT COUNT(*) FROM companies`
- Check signal has `signal_description` or `signal_citation`
- Try lowering `CONFIDENCE_THRESHOLD` to `0.7`

### Daily sync timeout
- For millions of contacts, use `--companies-only` flag
- Run full sync in chunks over multiple days

### Embedding errors
- Verify OpenAI API key is valid
- Check rate limits (default: 3,000 RPM)

## 📈 Monitoring

- **GitHub Actions**: Check workflow runs and logs
- **Supabase Dashboard**: Monitor `companies` and `contacts` table counts
- **Supabase → match_history**: View all matching decisions
- **HubSpot Activity**: See created associations on Signal records

## 📝 License

MIT
