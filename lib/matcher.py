"""Signal Matcher

Core matching logic that:
1. Fetches signal data from HubSpot
2. Generates embedding from signal text
3. Searches for matching companies/contacts
4. Creates associations for confident matches
"""

import os
import traceback
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from .hubspot_client import HubSpotClient
from .supabase_client import SupabaseClient
from .embeddings import EmbeddingGenerator


def log(msg):
    """Log with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class MatchResult:
    """Result of a matching operation."""
    hubspot_id: str
    name: str
    match_type: str  # 'company' or 'contact'
    similarity: float
    association_created: bool = False


class SignalMatcher:
    """Matches HubSpot Signals to Companies and Contacts using semantic embeddings."""
    
    def __init__(
        self,
        hubspot_token: Optional[str] = None,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        confidence_threshold: float = 0.85
    ):
        """Initialize the signal matcher."""
        self.hubspot = HubSpotClient(access_token=hubspot_token)
        self.supabase = SupabaseClient(url=supabase_url, key=supabase_key)
        self.embeddings = EmbeddingGenerator(api_key=openai_key)
        self.threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", confidence_threshold))
    
    def match_signal(self, signal_id: str) -> dict:
        """Match a signal to companies and/or contacts."""
        log(f"Processing signal {signal_id}...")
        
        try:
            # 1. Fetch signal from HubSpot
            signal = self.hubspot.get_signal(signal_id)
            properties = signal["properties"]
            
            signal_type = properties.get("signal_type") or "company"
            description = properties.get("signal_description", "") or ""
            citation = properties.get("signal_citation", "") or ""
            
            log(f"  Signal type: {signal_type}")
            log(f"  Description: {description[:100]}..." if len(description) > 100 else f"  Description: {description}")
            
            # Check existing associations
            existing_companies = signal["associations"].get("companies", [])
            existing_contacts = signal["associations"].get("contacts", [])
            
            if existing_companies or existing_contacts:
                log(f"  Signal already has: {len(existing_companies)} companies, {len(existing_contacts)} contacts")
            
            # 2. Generate embedding
            signal_text = self.embeddings.prepare_signal_text(description, citation)
            
            if not signal_text.strip():
                log("  ERROR: No text content in signal to match")
                return {
                    "signal_id": signal_id,
                    "signal_type": signal_type,
                    "error": "No text content to match",
                    "company_matches": [],
                    "contact_matches": [],
                    "total_matches": 0,
                    "associations_created": 0
                }
            
            log(f"  Generating embedding for: {signal_text[:100]}...")
            signal_embedding = self.embeddings.generate_embedding(signal_text)
            
            # 3. Search for matches
            company_matches: List[MatchResult] = []
            contact_matches: List[MatchResult] = []
            
            if signal_type in ["company", "company_contact", None, ""]:
                log(f"  Searching companies (threshold: {self.threshold})...")
                company_results = self.supabase.search_companies(
                    embedding=signal_embedding,
                    threshold=self.threshold,
                    limit=10
                )
                
                for result in company_results:
                    match = MatchResult(
                        hubspot_id=result["hubspot_id"],
                        name=result.get("name", "Unknown"),
                        match_type="company",
                        similarity=result["similarity"]
                    )
                    company_matches.append(match)
                    log(f"    Company match: {match.name} ({match.similarity:.1%})")
            
            if signal_type in ["contact", "company_contact"]:
                log(f"  Searching contacts (threshold: {self.threshold})...")
                contact_results = self.supabase.search_contacts(
                    embedding=signal_embedding,
                    threshold=self.threshold,
                    limit=10
                )
                
                for result in contact_results:
                    full_name = " ".join(filter(None, [
                        result.get("firstname", ""),
                        result.get("lastname", "")
                    ])) or "Unknown"
                    
                    match = MatchResult(
                        hubspot_id=result["hubspot_id"],
                        name=full_name,
                        match_type="contact",
                        similarity=result["similarity"]
                    )
                    contact_matches.append(match)
                    log(f"    Contact match: {match.name} ({match.similarity:.1%})")
            
            # 4. Create associations
            associations_created = 0
            
            for match in company_matches:
                if match.hubspot_id not in existing_companies:
                    success = self.hubspot.create_signal_company_association(
                        signal_id=signal_id,
                        company_id=match.hubspot_id
                    )
                    match.association_created = success
                    if success:
                        associations_created += 1
                        log(f"    Created: Signal -> {match.name}")
                    
                    self.supabase.log_match(
                        signal_id=signal_id,
                        matched_type="company",
                        matched_hubspot_id=match.hubspot_id,
                        confidence=match.similarity,
                        association_created=success
                    )
                else:
                    log(f"    Skipped {match.name} (already associated)")
            
            for match in contact_matches:
                if match.hubspot_id not in existing_contacts:
                    success = self.hubspot.create_signal_contact_association(
                        signal_id=signal_id,
                        contact_id=match.hubspot_id
                    )
                    match.association_created = success
                    if success:
                        associations_created += 1
                        log(f"    Created: Signal -> {match.name}")
                    
                    self.supabase.log_match(
                        signal_id=signal_id,
                        matched_type="contact",
                        matched_hubspot_id=match.hubspot_id,
                        confidence=match.similarity,
                        association_created=success
                    )
                else:
                    log(f"    Skipped {match.name} (already associated)")
            
            # 5. Return results
            result = {
                "signal_id": signal_id,
                "signal_type": signal_type,
                "signal_text": signal_text[:200],
                "company_matches": [
                    {
                        "hubspot_id": m.hubspot_id,
                        "name": m.name,
                        "similarity": m.similarity,
                        "association_created": m.association_created
                    }
                    for m in company_matches
                ],
                "contact_matches": [
                    {
                        "hubspot_id": m.hubspot_id,
                        "name": m.name,
                        "similarity": m.similarity,
                        "association_created": m.association_created
                    }
                    for m in contact_matches
                ],
                "total_matches": len(company_matches) + len(contact_matches),
                "associations_created": associations_created
            }
            
            if not company_matches and not contact_matches:
                log(f"  No matches found above {self.threshold:.0%} threshold")
            else:
                log(f"  Completed: {result['total_matches']} matches, {associations_created} associations created")
            
            return result
            
        except Exception as e:
            log(f"  ERROR processing signal: {e}")
            traceback.print_exc()
            return {
                "signal_id": signal_id,
                "error": str(e),
                "company_matches": [],
                "contact_matches": [],
                "total_matches": 0,
                "associations_created": 0
            }


def match_signal_standalone(signal_id: str) -> dict:
    """Standalone function to match a signal."""
    matcher = SignalMatcher()
    return matcher.match_signal(signal_id)
