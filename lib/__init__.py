"""
HubSpot Signal Matcher Library

Core modules for matching HubSpot Signals to Companies and Contacts
using semantic embeddings and vector similarity search.
"""

from .hubspot_client import HubSpotClient
from .supabase_client import SupabaseClient
from .embeddings import EmbeddingGenerator
from .matcher import SignalMatcher

__all__ = [
    "HubSpotClient",
    "SupabaseClient", 
    "EmbeddingGenerator",
    "SignalMatcher",
]