"""
Signal Matcher - Company Name Extraction Approach

Matches HubSpot Signals to Companies by:
1. Extracting company names from signal text using OpenAI
2. Searching for those companies by name in Supabase
3. Creating associations for matches
"""

import os
import json
import traceback
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from openai import OpenAI

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
    """Matches HubSpot Signals to Companies using name extraction."""
    
    def __init__(
        self,
        hubspot_token: Optional[str] = None,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        confidence_threshold: float = 0.80
    ):
        """Initialize the signal matcher."""
        self.hubspot = HubSpotClient(access_token=hubspot_token)
        self.supabase = SupabaseClient(url=supabase_url, key=supabase_key)
        self.embeddings = EmbeddingGenerator(api_key=openai_key)
        self.threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", confidence_threshold))
        
        # Initialize OpenAI client for name extraction
        api_key = openai_key or os.environ.get("OPENAI_API_KEY")
        self.openai = OpenAI(api_key=api_key)
    
    def extract_company_names(self, text: str) -> List[str]:
        """
        Extract company/brand names from signal text using OpenAI.
        
        Args:
            text: Signal description and citation text
            
        Returns:
            List of company names mentioned in the text
        """
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """Extract all company, brand, or organization names from the text.
Return ONLY a JSON array of strings with the exact company names as they appear.
Do not include generic terms like "the company" or person names.
If no companies are mentioned, return an empty array [].

Examples:
- "GoPro's headquarters will be demolished" -> ["GoPro"]
- "Ted Baker launches Ted Baker Sport" -> ["Ted Baker"]
- "L'Oreal and Pernod Ricard executives visit India" -> ["L'Oreal", "Pernod Ricard"]
- "The new store opened downtown" -> []"""
                    },
                    {
                        "role": "user",
                        "content": text[:2000]  # Limit to 2000 chars
                    }
                ],
                temperature=0,
                max_tokens=500
            )
            
            result = response.choices[0].message.content.strip()
            # Parse JSON array
            if result.startswith("["):
                companies = json.loads(result)
                return [c.strip() for c in companies if c and isinstance(c, str)]
            return []
            
        except Exception as e:
            log(f"  Error extracting company names: {e}")
            return []
    
    def search_company_by_name(self, company_name: str) -> List[dict]:
        """
        Search for a company by name in Supabase using text matching.
        
        Args:
            company_name: Name to search for
            
        Returns:
            List of matching company records
        """
        try:
            # Use Supabase client to search by name
            results = self.supabase.client.table("companies").select(
                "hubspot_id, name, domain"
            ).or_(
                f"name.ilike.%{company_name}%,domain.ilike.%{company_name}%"
            ).limit(5).execute()
            
            matches = []
            for record in results.data:
                # Calculate a simple similarity score based on name match
                name_lower = record["name"].lower() if record["name"] else ""
                search_lower = company_name.lower()
                
                # Exact match = 1.0, contains = 0.9, partial = 0.8
                if name_lower == search_lower:
                    similarity = 1.0
                elif search_lower in name_lower or name_lower in search_lower:
                    similarity = 0.9
                else:
                    similarity = 0.8
                
                matches.append({
                    "hubspot_id": record["hubspot_id"],
                    "name": record["name"],
                    "domain": record.get("domain", ""),
                    "similarity": similarity
                })
            
            return matches
            
        except Exception as e:
            log(f"  Error searching for '{company_name}': {e}")
            return []
    
    def match_signal(self, signal_id: str) -> dict:
        """Match a signal to companies using name extraction."""
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
                log(f"  Already has: {len(existing_companies)} companies, {len(existing_contacts)} contacts")
            
            # Combine text for extraction
            full_text = f"{description} {citation}".strip()
            
            if not full_text:
                log("  ERROR: No text content in signal")
                return {
                    "signal_id": signal_id,
                    "signal_type": signal_type,
                    "error": "No text content",
                    "company_matches": [],
                    "contact_matches": [],
                    "total_matches": 0,
                    "associations_created": 0
                }
            
            # 2. Extract company names from text
            log("  Extracting company names...")
            company_names = self.extract_company_names(full_text)
            log(f"  Found companies: {company_names}")
            
            if not company_names:
                log("  No company names found in text")
                return {
                    "signal_id": signal_id,
                    "signal_type": signal_type,
                    "extracted_companies": [],
                    "company_matches": [],
                    "contact_matches": [],
                    "total_matches": 0,
                    "associations_created": 0
                }
            
            # 3. Search for each company name
            company_matches: List[MatchResult] = []
            seen_ids = set()  # Avoid duplicates
            
            for company_name in company_names:
                log(f"  Searching for: {company_name}")
                results = self.search_company_by_name(company_name)
                
                for result in results:
                    if result["hubspot_id"] not in seen_ids and result["similarity"] >= self.threshold:
                        seen_ids.add(result["hubspot_id"])
                        match = MatchResult(
                            hubspot_id=result["hubspot_id"],
                            name=result["name"],
                            match_type="company",
                            similarity=result["similarity"]
                        )
                        company_matches.append(match)
                        log(f"    Match: {match.name} ({match.similarity:.0%})")
            
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
            
            # 5. Return results
            result = {
                "signal_id": signal_id,
                "signal_type": signal_type,
                "extracted_companies": company_names,
                "company_matches": [
                    {
                        "hubspot_id": m.hubspot_id,
                        "name": m.name,
                        "similarity": m.similarity,
                        "association_created": m.association_created
                    }
                    for m in company_matches
                ],
                "contact_matches": [],
                "total_matches": len(company_matches),
                "associations_created": associations_created
            }
            
            if company_matches:
                log(f"  Completed: {len(company_matches)} matches, {associations_created} associations")
            else:
                log(f"  No matches found in database for: {company_names}")
            
            return result
            
        except Exception as e:
            log(f"  ERROR: {e}")
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
