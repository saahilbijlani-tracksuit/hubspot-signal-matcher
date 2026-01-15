"""Signal Matcher - Company Name Extraction with Assignment Logic

Matches HubSpot Signals to Companies by:
1. Extracting company names from signal text using OpenAI
2. Searching for those companies by name in Supabase
3. Selecting best match (highest score, tie-break by stage)
4. Creating associations for matches
5. Assigning signal owner and shared users based on company stage
6. Sending Slack notification
"""

import os
import json
import traceback
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI

from .hubspot_client import HubSpotClient
from .supabase_client import SupabaseClient
from .embeddings import EmbeddingGenerator
from .slack_client import SlackClient


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class MatchResult:
    hubspot_id: str
    name: str
    match_type: str
    similarity: float
    association_created: bool = False
    stage: str = ""
    owner_id: str = ""
    shared_user_ids: List[str] = field(default_factory=list)


class SignalMatcher:
    STAGE_PRIORITY = {"Customer": 3, "Prospect": 2, "Agency": 1}
    CUSTOMER_STAGES = ["customer", "1105763437"]

    def __init__(self, hubspot_token=None, supabase_url=None, supabase_key=None, openai_key=None, confidence_threshold=0.80, enable_slack=True):
        self.hubspot = HubSpotClient(access_token=hubspot_token)
        self.supabase = SupabaseClient(url=supabase_url, key=supabase_key)
        self.embeddings = EmbeddingGenerator(api_key=openai_key)
        self.threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", confidence_threshold))
        api_key = openai_key or os.environ.get("OPENAI_API_KEY")
        self.openai = OpenAI(api_key=api_key)
        self.slack = SlackClient() if enable_slack else None

    def determine_company_stage(self, company_details: dict) -> str:
        lifecyclestage = company_details.get("lifecyclestage", "").lower()
        company_type = company_details.get("company_type", "").lower()
        if company_type == "agency":
            return "Agency"
        if lifecyclestage in self.CUSTOMER_STAGES:
            return "Customer"
        return "Prospect"

    def get_assignment_for_stage(self, stage: str, company_details: dict) -> Tuple[str, List[str]]:
        ae_owner = company_details.get("ae_owner", "")
        sdr_owner = company_details.get("sdr_owner", "")
        brand_champ = company_details.get("brand_champ", "")
        company_owner = company_details.get("hubspot_owner_id", "")

        if stage == "Prospect":
            owner_id = ae_owner or company_owner
            shared_ids = [uid for uid in [sdr_owner, company_owner] if uid and uid != owner_id]
        elif stage == "Customer":
            owner_id = brand_champ or company_owner
            shared_ids = [company_owner] if company_owner and company_owner != owner_id else []
        else:
            owner_id = company_owner
            shared_ids = []
        return owner_id, shared_ids

    def select_best_match(self, matches: List[MatchResult]) -> Optional[MatchResult]:
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        def sort_key(m):
            return (m.similarity, self.STAGE_PRIORITY.get(m.stage, 0))
        return sorted(matches, key=sort_key, reverse=True)[0]

    def extract_company_names(self, text: str) -> List[str]:
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """Extract all company, brand, or organization names from the text.
Return ONLY a JSON array of strings with the exact company names as they appear.
Do not include generic terms like "the company" or person names.
If no companies are mentioned, return an empty array [].

Examples:
- "GoPro's headquarters will be demolished" -> ["GoPro"]
- "Ted Baker launches Ted Baker Sport" -> ["Ted Baker"]
- "L'Oreal and Pernod Ricard executives visit India" -> ["L'Oreal", "Pernod Ricard"]
- "The new store opened downtown" -> []"""},
                    {"role": "user", "content": text[:2000]}
                ],
                temperature=0,
                max_tokens=500
            )
            result = response.choices[0].message.content.strip()
            if result.startswith("["):
                companies = json.loads(result)
                return [c.strip() for c in companies if c and isinstance(c, str)]
            return []
        except Exception as e:
            log(f"  Error extracting company names: {e}")
            return []

    def search_company_by_name(self, company_name: str) -> List[dict]:
        try:
            sanitized_name = company_name.replace(",", "").replace(".", "").replace("'", "''")
            results = self.supabase.client.table("companies").select(
                "hubspot_id, name, domain"
            ).or_(f"name.ilike.%{sanitized_name}%,domain.ilike.%{sanitized_name}%").limit(5).execute()

            matches = []
            for record in results.data:
                name_lower = record["name"].lower() if record["name"] else ""
                search_lower = company_name.lower()
                if name_lower == search_lower:
                    similarity = 1.0
                elif search_lower in name_lower or name_lower in search_lower:
                    similarity = 0.9
                else:
                    similarity = 0.8
                matches.append({"hubspot_id": record["hubspot_id"], "name": record["name"], "domain": record.get("domain", ""), "similarity": similarity})
            return matches
        except Exception as e:
            log(f"  Error searching for '{company_name}': {e}")
            return []

    def match_signal(self, signal_id: str, notify_slack: bool = True) -> dict:
        log(f"Processing signal {signal_id}...")
        try:
            signal = self.hubspot.get_signal(signal_id)
            properties = signal["properties"]
            signal_type = properties.get("signal_type") or "company"
            signal_name = properties.get("signal_name") or "Signal"
            description = properties.get("signal_description", "") or ""
            citation = properties.get("signal_citation", "") or ""

            log(f"  Signal type: {signal_type}")
            log(f"  Description: {description[:100]}..." if len(description) > 100 else f"  Description: {description}")

            existing_companies = signal["associations"].get("companies", [])
            existing_contacts = signal["associations"].get("contacts", [])
            if existing_companies or existing_contacts:
                log(f"  Already has: {len(existing_companies)} companies, {len(existing_contacts)} contacts")

            full_text = f"{description} {citation}".strip()
            if not full_text:
                log("  ERROR: No text content in signal")
                return {"signal_id": signal_id, "signal_type": signal_type, "error": "No text content", "company_matches": [], "contact_matches": [], "total_matches": 0, "associations_created": 0}

            log("  Extracting company names...")
            company_names = self.extract_company_names(full_text)
            log(f"  Found companies: {company_names}")

            if not company_names:
                log("  No company names found in text")
                if notify_slack and self.slack:
                    self.slack.notify_signal_no_match(signal_id=signal_id, signal_name=signal_name, signal_description=description, extracted_companies=[])
                return {"signal_id": signal_id, "signal_type": signal_type, "extracted_companies": [], "company_matches": [], "contact_matches": [], "total_matches": 0, "associations_created": 0}

            all_matches = []
            seen_ids = set()
            for company_name in company_names:
                log(f"  Searching for: {company_name}")
                results = self.search_company_by_name(company_name)
                for result in results:
                    if result["hubspot_id"] not in seen_ids and result["similarity"] >= self.threshold:
                        seen_ids.add(result["hubspot_id"])
                        company_details = self.hubspot.get_company_details(result["hubspot_id"])
                        stage = self.determine_company_stage(company_details)
                        owner_id, shared_ids = self.get_assignment_for_stage(stage, company_details)
                        match = MatchResult(hubspot_id=result["hubspot_id"], name=result["name"], match_type="company", similarity=result["similarity"], stage=stage, owner_id=owner_id, shared_user_ids=shared_ids)
                        all_matches.append(match)
                        log(f"    Match: {match.name} ({match.similarity:.0%}) - {stage}")

            if not all_matches:
                log(f"  No matches found in database for: {company_names}")
                if notify_slack and self.slack:
                    self.slack.notify_signal_no_match(signal_id=signal_id, signal_name=signal_name, signal_description=description, extracted_companies=company_names)
                return {"signal_id": signal_id, "signal_type": signal_type, "extracted_companies": company_names, "company_matches": [], "contact_matches": [], "total_matches": 0, "associations_created": 0}

            best_match = self.select_best_match(all_matches)
            log(f"  Best match for assignment: {best_match.name} ({best_match.stage})")

            associations_created = 0
            for match in all_matches:
                if match.hubspot_id not in existing_companies:
                    success = self.hubspot.create_signal_company_association(signal_id=signal_id, company_id=match.hubspot_id)
                    match.association_created = success
                    if success:
                        associations_created += 1
                        log(f"    Created: Signal -> {match.name}")
                    self.supabase.log_match(signal_id=signal_id, matched_type="company", matched_hubspot_id=match.hubspot_id, confidence=match.similarity, association_created=success)
                else:
                    log(f"    Skipped {match.name} (already associated)")

            owner_name = ""
            shared_user_names = []
            if best_match.owner_id:
                log(f"  Assigning owner: {best_match.owner_id}")
                owner_success = self.hubspot.update_signal_owner(signal_id, best_match.owner_id)
                if owner_success:
                    owner_name = self.hubspot.get_owner_name(best_match.owner_id)
                    log(f"    Owner set: {owner_name}")
                else:
                    log(f"    Failed to set owner")

            if best_match.shared_user_ids:
                log(f"  Assigning shared users: {best_match.shared_user_ids}")
                shared_success = self.hubspot.update_signal_shared_users(signal_id, best_match.shared_user_ids)
                if shared_success:
                    shared_user_names = [self.hubspot.get_owner_name(uid) for uid in best_match.shared_user_ids]
                    log(f"    Shared users set: {shared_user_names}")

            if notify_slack and self.slack and best_match.association_created:
                self.slack.notify_signal_matched(signal_id=signal_id, signal_name=signal_name, signal_description=description, company_name=best_match.name, company_id=best_match.hubspot_id, company_stage=best_match.stage, confidence=best_match.similarity, owner_name=owner_name, shared_users=shared_user_names)

            result = {
                "signal_id": signal_id, "signal_type": signal_type, "extracted_companies": company_names,
                "company_matches": [{"hubspot_id": m.hubspot_id, "name": m.name, "similarity": m.similarity, "stage": m.stage, "association_created": m.association_created} for m in all_matches],
                "best_match": {"hubspot_id": best_match.hubspot_id, "name": best_match.name, "stage": best_match.stage, "owner_assigned": owner_name, "shared_users": shared_user_names},
                "contact_matches": [], "total_matches": len(all_matches), "associations_created": associations_created
            }
            log(f"  Completed: {len(all_matches)} matches, {associations_created} associations")
            return result
        except Exception as e:
            log(f"  ERROR: {e}")
            traceback.print_exc()
            return {"signal_id": signal_id, "error": str(e), "company_matches": [], "contact_matches": [], "total_matches": 0, "associations_created": 0}


def match_signal_standalone(signal_id: str) -> dict:
    matcher = SignalMatcher()
    return matcher.match_signal(signal_id)
