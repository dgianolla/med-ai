-- ============================================================
-- Migração 001 — Schema inicial med-ai
-- ============================================================

-- Extensão para UUIDs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- PACIENTES
-- ============================================================
CREATE TABLE IF NOT EXISTS patients (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone                 VARCHAR(20) UNIQUE NOT NULL,        -- ex: 5511988579353
    wts_contact_id        UUID,                               -- ID do contato no wts.chat
    name                  VARCHAR(255),
    cpf_encrypted         BYTEA,                             -- AES-256 (aplicado na aplicação)
    date_of_birth         DATE,
    lgpd_consent_at       TIMESTAMPTZ,
    lgpd_consent_version  VARCHAR(10),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);
CREATE INDEX IF NOT EXISTS idx_patients_wts_contact_id ON patients(wts_contact_id);

-- ============================================================
-- SESSÕES
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id                  VARCHAR(100) PRIMARY KEY,             -- phone_timestamp ex: 5511988579353_1711234567
    patient_id          UUID REFERENCES patients(id) ON DELETE SET NULL,
    wts_session_id      UUID,                                 -- sessionId do wts.chat (usado no envio)
    current_agent       VARCHAR(50) NOT NULL,                 -- triage | scheduling | exams | commercial | return
    status              VARCHAR(20) NOT NULL DEFAULT 'active',-- active | completed | expired
    handoff_payload     JSONB,
    last_message_preview TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_patient_id ON sessions(patient_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_wts_session_id ON sessions(wts_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity_at DESC);

-- ============================================================
-- MENSAGENS
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    wts_message_id UUID,                                      -- ID da mensagem no wts.chat
    agent_id      VARCHAR(50),                                -- qual agente gerou/recebeu
    role          VARCHAR(15) NOT NULL,                       -- user | assistant | tool | system
    message_type  VARCHAR(20) NOT NULL DEFAULT 'text',        -- text | audio | image | pdf
    content       TEXT NOT NULL,                              -- texto (ou transcrição/extração para mídia)
    file_url      TEXT,                                       -- URL original do arquivo (se mídia)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);

-- ============================================================
-- AUDIT LOG (LGPD)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id   UUID REFERENCES patients(id) ON DELETE SET NULL,
    session_id   VARCHAR(100),
    event_type   VARCHAR(100) NOT NULL,                       -- consent_given | data_deleted | agent_handoff | etc
    event_data   JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_patient_id ON audit_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);

-- ============================================================
-- VIEW — Painel CRM (sessões ativas com dados do paciente)
-- ============================================================
CREATE OR REPLACE VIEW active_sessions_view AS
SELECT
    s.id                    AS session_id,
    s.wts_session_id,
    s.current_agent,
    s.status,
    s.last_message_preview,
    s.started_at,
    s.last_activity_at,
    p.id                    AS patient_id,
    p.name                  AS patient_name,
    p.phone                 AS patient_phone,
    EXTRACT(EPOCH FROM (now() - s.last_activity_at)) / 60 AS minutes_since_last_message
FROM sessions s
LEFT JOIN patients p ON s.patient_id = p.id
WHERE s.status = 'active'
ORDER BY s.last_activity_at DESC;

-- ============================================================
-- FUNÇÃO — Atualiza updated_at automaticamente em patients
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
