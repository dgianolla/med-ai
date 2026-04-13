-- ============================================================
-- Migração 003 — Generalização de priority_leads para atenção comercial
-- ============================================================

ALTER TABLE priority_leads
    ADD COLUMN IF NOT EXISTS convenio VARCHAR(50),
    ADD COLUMN IF NOT EXISTS specialty VARCHAR(100),
    ADD COLUMN IF NOT EXISTS source_agent VARCHAR(50),
    ADD COLUMN IF NOT EXISTS campaign_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS summary TEXT,
    ADD COLUMN IF NOT EXISTS action_label TEXT,
    ADD COLUMN IF NOT EXISTS priority_type VARCHAR(50) NOT NULL DEFAULT 'high_ticket',
    ADD COLUMN IF NOT EXISTS priority_score INTEGER NOT NULL DEFAULT 50,
    ADD COLUMN IF NOT EXISTS metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_priority_leads_priority_type ON priority_leads(priority_type);
CREATE INDEX IF NOT EXISTS idx_priority_leads_priority_score ON priority_leads(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_priority_leads_source_agent ON priority_leads(source_agent);
