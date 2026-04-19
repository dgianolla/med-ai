-- ============================================================
-- Migração 004 — Sessão Helena em confirmações
-- ============================================================

ALTER TABLE schedule_confirmations
    ADD COLUMN IF NOT EXISTS helena_session_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_schedule_confirmations_helena_session_id
    ON schedule_confirmations(helena_session_id);
