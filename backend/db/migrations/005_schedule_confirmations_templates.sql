-- ============================================================
-- Migração 005 — Template usado no disparo de confirmações
-- ============================================================

ALTER TABLE schedule_confirmations
    ADD COLUMN IF NOT EXISTS template_key VARCHAR(50),
    ADD COLUMN IF NOT EXISTS template_version VARCHAR(30);
