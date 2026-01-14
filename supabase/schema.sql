-- HubSpot Signal Matcher - Supabase Schema
-- Run this in your Supabase SQL Editor

-- Enable the pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- COMPANIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS companies (
    id BIGSERIAL PRIMARY KEY,
    hubspot_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    domain TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    embedded_text TEXT
);

CREATE INDEX IF NOT EXISTS companies_embedding_idx 
ON companies 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS companies_hubspot_id_idx 
ON companies (hubspot_id);

-- ============================================
-- CONTACTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS contacts (
    id BIGSERIAL PRIMARY KEY,
    hubspot_id TEXT UNIQUE NOT NULL,
    firstname TEXT,
    lastname TEXT,
    company TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    embedded_text TEXT
);

CREATE INDEX IF NOT EXISTS contacts_embedding_idx 
ON contacts 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS contacts_hubspot_id_idx 
ON contacts (hubspot_id);

-- ============================================
-- SYNC METADATA TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS sync_metadata (
    id SERIAL PRIMARY KEY,
    entity_type TEXT UNIQUE NOT NULL,
    last_sync_at TIMESTAMPTZ DEFAULT NOW(),
    records_synced INTEGER DEFAULT 0
);

INSERT INTO sync_metadata (entity_type, last_sync_at, records_synced)
VALUES 
    ('companies', '1970-01-01'::TIMESTAMPTZ, 0),
    ('contacts', '1970-01-01'::TIMESTAMPTZ, 0)
ON CONFLICT (entity_type) DO NOTHING;

-- ============================================
-- MATCH HISTORY TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS match_history (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL,
    matched_type TEXT NOT NULL,
    matched_hubspot_id TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    association_created BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS match_history_signal_idx 
ON match_history (signal_id);

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

CREATE OR REPLACE FUNCTION search_companies(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.85,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    hubspot_id TEXT,
    name TEXT,
    domain TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.hubspot_id,
        c.name,
        c.domain,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM companies c
    WHERE c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) >= match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION search_contacts(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.85,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    hubspot_id TEXT,
    firstname TEXT,
    lastname TEXT,
    company TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.hubspot_id,
        c.firstname,
        c.lastname,
        c.company,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM contacts c
    WHERE c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) >= match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- View to check embedding coverage
CREATE OR REPLACE VIEW embedding_stats AS
SELECT 
    'companies' as entity_type,
    COUNT(*) as total_records,
    COUNT(embedding) as records_with_embeddings,
    ROUND(100.0 * COUNT(embedding) / NULLIF(COUNT(*), 0), 2) as coverage_percent
FROM companies
UNION ALL
SELECT 
    'contacts' as entity_type,
    COUNT(*) as total_records,
    COUNT(embedding) as records_with_embeddings,
    ROUND(100.0 * COUNT(embedding) / NULLIF(COUNT(*), 0), 2) as coverage_percent
FROM contacts;