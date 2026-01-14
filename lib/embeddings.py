"""OpenAI Embedding Generator

Handles text embedding generation using OpenAI's API:
- Single text embedding
- Batch embedding with rate limiting
- Text preprocessing for optimal embeddings
"""

import os
import time
from typing import List, Optional
from openai import OpenAI


class EmbeddingGenerator:
    """Generator for OpenAI text embeddings."""
    
    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536
    MAX_TOKENS_PER_REQUEST = 8000
    MAX_REQUESTS_PER_MINUTE = 3000
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize embedding generator."""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        
        self.client = OpenAI(api_key=self.api_key)
        self._request_count = 0
        self._minute_start = time.time()
    
    def _rate_limit(self):
        """Simple rate limiting to avoid hitting OpenAI limits."""
        self._request_count += 1
        
        if time.time() - self._minute_start > 60:
            self._request_count = 0
            self._minute_start = time.time()
        
        if self._request_count >= self.MAX_REQUESTS_PER_MINUTE - 100:
            sleep_time = 60 - (time.time() - self._minute_start)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self._request_count = 0
            self._minute_start = time.time()
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            return [0.0] * self.DIMENSIONS
        
        max_chars = self.MAX_TOKENS_PER_REQUEST * 4
        if len(text) > max_chars:
            text = text[:max_chars]
        
        self._rate_limit()
        
        response = self.client.embeddings.create(
            model=self.MODEL,
            input=text,
            dimensions=self.DIMENSIONS
        )
        
        return response.data[0].embedding
    
    def generate_embeddings_batch(
        self, 
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches."""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            processed_batch = []
            empty_indices = []
            
            for j, text in enumerate(batch):
                if text and text.strip():
                    max_chars = self.MAX_TOKENS_PER_REQUEST * 4
                    processed_batch.append(text[:max_chars] if len(text) > max_chars else text)
                else:
                    empty_indices.append(j)
            
            self._rate_limit()
            
            if processed_batch:
                response = self.client.embeddings.create(
                    model=self.MODEL,
                    input=processed_batch,
                    dimensions=self.DIMENSIONS
                )
                
                batch_embeddings = [e.embedding for e in response.data]
                
                result = []
                embedding_idx = 0
                for j in range(len(batch)):
                    if j in empty_indices:
                        result.append([0.0] * self.DIMENSIONS)
                    else:
                        result.append(batch_embeddings[embedding_idx])
                        embedding_idx += 1
                
                embeddings.extend(result)
            else:
                embeddings.extend([[0.0] * self.DIMENSIONS] * len(batch))
        
        return embeddings
    
    # ==========================================
    # TEXT PREPARATION HELPERS
    # ==========================================
    
    @staticmethod
    def prepare_company_text(name: str, domain: str) -> str:
        """Prepare company text for embedding."""
        parts = []
        if name:
            parts.append(f"Company: {name}")
        if domain:
            parts.append(f"Domain: {domain}")
        return " | ".join(parts) if parts else ""
    
    @staticmethod
    def prepare_contact_text(firstname: str, lastname: str, company: str) -> str:
        """Prepare contact text for embedding."""
        parts = []
        full_name = " ".join(filter(None, [firstname, lastname]))
        if full_name:
            parts.append(f"Person: {full_name}")
        if company:
            parts.append(f"Company: {company}")
        return " | ".join(parts) if parts else ""
    
    @staticmethod
    def prepare_signal_text(description: str, citation: str) -> str:
        """Prepare signal text for embedding."""
        parts = []
        if description:
            parts.append(description)
        if citation:
            parts.append(f"Source: {citation}")
        return " | ".join(parts) if parts else ""
