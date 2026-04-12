-- ============================================================
-- Migração 002 — Fila de encaixe prioritário (canetas / endócrino)
-- ============================================================
-- Leads de alto ticket (protocolo de canetas injetáveis) que não
-- conseguiram slot na agenda do endocrinologista entram nesta fila
-- para a equipe comercial fazer encaixe manual.
-- ============================================================

CREATE TABLE IF NOT EXISTS priority_leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID REFERENCES patients(id) ON DELETE SET NULL,
    session_id          VARCHAR(100) REFERENCES sessions(id) ON DELETE SET NULL,
    patient_name        VARCHAR(255),
    patient_phone       VARCHAR(20) NOT NULL,
    interest            VARCHAR(50) NOT NULL DEFAULT 'canetas',  -- canetas | outros
    caneta_preferida    VARCHAR(50),                             -- ozempic | mounjaro | indeciso
    periodo_preferido   VARCHAR(50),                             -- manha | tarde | qualquer
    professional_id     INTEGER,                                  -- ID do profissional alvo (Dr. Arthur = 30319)
    professional_name   VARCHAR(255),
    notes               TEXT,                                     -- objeção, contexto, observações do lead
    status              VARCHAR(20) NOT NULL DEFAULT 'aguardando',
                                                                  -- aguardando | em_contato | agendado | descartado
    handled_by          VARCHAR(255),                             -- usuário do painel que pegou o lead
    handled_at          TIMESTAMPTZ,
    appointment_id      VARCHAR(50),                              -- ID do agendamento manual quando concluído
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_priority_leads_status        ON priority_leads(status);
CREATE INDEX IF NOT EXISTS idx_priority_leads_patient_phone ON priority_leads(patient_phone);
CREATE INDEX IF NOT EXISTS idx_priority_leads_created_at    ON priority_leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_priority_leads_interest      ON priority_leads(interest);

-- Trigger para manter updated_at
CREATE OR REPLACE FUNCTION update_priority_leads_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_priority_leads_updated_at ON priority_leads;
CREATE TRIGGER trg_priority_leads_updated_at
    BEFORE UPDATE ON priority_leads
    FOR EACH ROW
    EXECUTE FUNCTION update_priority_leads_updated_at();
