"""Supabase Vector Database Client

Handles all vector storage and similarity search operations:
- Storing company/contact embeddings
- Vector similarity search for matching
- Sync metadata tracking
"""

import os
from typing import Optional, List
from supabase import create_client, Client


class SupabaseClient:
    """Client for Supabase vector database operations."""
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client."""
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and key required")
        
        self.client: Client = create_client(self.url, self.key)
    
    # ==========================================
    # COMPANY OPERATIONS
    # ==========================================
    
    def upsert_company(
        self,
        hubspot_id: str,
        name: str,
        domain: str,
        embedding: List[float],
        embedded_text: str
    ) -> bool:
        """Insert or update a company embedding."""
        try:
            self.client.table("companies").upsert({
                "hubspot_id": hubspot_id,
                "name": name,
                "domain": domain,
                "embedding": embedding,
                "embedded_text": embedded_text
            }, on_conflict="hubspot_id").execute()
            return True
        except Exception as e:
            print(f"Error upserting company {hubspot_id}: {e}")
            return False
    
    def upsert_companies_batch(self, companies: List[dict]) -> int:
        """Batch upsert multiple companies."""
        try:
            self.client.table("companies").upsert(
                companies,
                on_conflict="hubspot_id"
            ).execute()
            return len(companies)
        except Exception as e:
            print(f"Error batch upserting companies: {e}")
            return 0
    
    def search_companies(
        self,
        embedding: List[float],
        threshold: float = 0.85,
        limit: int = 10
    ) -> List[dict]:
        """Search for companies by embedding similarity."""
        try:
            response = self.client.rpc(
                "search_companies",
                {
                    "query_embedding": embedding,
                    "match_threshold": threshold,
                    "match_count": limit
                }
            ).execute()
            return response.data or []
        except Exception as e:
            print(f"Error searching companies: {e}")
            return []
    
    def get_company_count(self) -> int:
        """Get total number of companies in the database."""
        try:
            response = self.client.table("companies").select("id", count="exact").execute()
            return response.count or 0
        except Exception:
            return 0
    
    # ==========================================
    # CONTACT OPERATIONS
    # ==========================================
    
    def upsert_contact(
        self,
        hubspot_id: str,
        firstname: str,
        lastname: str,
        company: str,
        embedding: List[float],
        embedded_text: str
    ) -> bool:
        """Insert or update a contact embedding."""
        try:
            self.client.table("contacts").upsert({
                "hubspot_id": hubspot_id,
                "firstname": firstname,
                "lastname": lastname,
                "company": company,
                "embedding": embedding,
                "embedded_text": embedded_text
            }, on_conflict="hubspot_id").execute()
            return True
        except Exception as e:
            print(f"Error upserting contact {hubspot_id}: {e}")
            return False
    
    def upsert_contacts_batch(self, contacts: List[dict]) -> int:
        """Batch upsert multiple contacts."""
        try:
            self.client.table("contacts").upsert(
                contacts,
                on_conflict="hubspot_id"
            ).execute()
            return len(contacts)
        except Exception as e:
            print(f"Error batch upserting contacts: {e}")
            return 0
    
    def search_contacts(
        self,
        embedding: List[float],
        threshold: float = 0.85,
        limit: int = 10
    ) -> List[dict]:
        """Search for contacts by embedding similarity."""
        try:
            response = self.client.rpc(
                "search_contacts",
                {
                    "query_embedding": embedding,
                    "match_threshold": threshold,
                    "match_count": limit
                }
            ).execute()
            return response.data or []
        except Exception as e:
            print(f"Error searching contacts: {e}")
            return []
    
    def get_contact_count(self) -> int:
        """Get total number of contacts in the database."""
        try:
            response = self.client.table("contacts").select("id", count="exact").execute()
            return response.count or 0
        except Exception:
            return 0
    
    # ==========================================
    # SYNC METADATA OPERATIONS
    # ==========================================
    
    def update_sync_metadata(self, entity_type: str, records_synced: int) -> bool:
        """Update sync metadata after a sync operation."""
        try:
            self.client.table("sync_metadata").upsert({
                "entity_type": entity_type,
                "last_sync_at": "now()",
                "records_synced": records_synced
            }, on_conflict="entity_type").execute()
            return True
        except Exception:
            return False
    
    def log_match(
        self,
        signal_id: str,
        matched_type: str,
        matched_hubspot_id: str,
        confidence: float,
        association_created: bool
    ) -> bool:
        """Log a match result for auditing."""
        try:
            self.client.table("match_history").insert({
                "signal_id": signal_id,
                "matched_type": matched_type,
                "matched_hubspot_id": matched_hubspot_id,
                "confidence": confidence,
                "association_created": association_created
            }).execute()
            return True
        except Exception:
            return False
