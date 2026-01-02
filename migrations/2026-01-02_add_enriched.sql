-- Adds enrichment tracking columns to MarketData
ALTER TABLE MarketData ADD COLUMN enriched INTEGER DEFAULT 0;
ALTER TABLE MarketData ADD COLUMN enriched_json TEXT;
