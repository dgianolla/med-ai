-- ============================================================
-- Migração 003 — Histórico de confirmações de agenda
-- ============================================================

CREATE TABLE IF NOT EXISTS schedule_confirmations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          VARCHAR(100),
    patient_name        VARCHAR(255),
    patient_phone       VARCHAR(20) NOT NULL,
    appointment_id      VARCHAR(50) NOT NULL,
    appointment_date    DATE NOT NULL,
    appointment_time    VARCHAR(20),
    professional_name   VARCHAR(255),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    message_id          VARCHAR(255),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_confirmations_appointment_id
    ON schedule_confirmations(appointment_id);

CREATE INDEX IF NOT EXISTS idx_schedule_confirmations_date
    ON schedule_confirmations(appointment_date);

CREATE INDEX IF NOT EXISTS idx_schedule_confirmations_status
    ON schedule_confirmations(status);

CREATE INDEX IF NOT EXISTS idx_schedule_confirmations_created_at
    ON schedule_confirmations(created_at DESC);

CREATE OR REPLACE FUNCTION update_schedule_confirmations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_schedule_confirmations_updated_at ON schedule_confirmations;
CREATE TRIGGER trg_schedule_confirmations_updated_at
    BEFORE UPDATE ON schedule_confirmations
    FOR EACH ROW
    EXECUTE FUNCTION update_schedule_confirmations_updated_at();
