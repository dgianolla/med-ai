export type AgentType = "triage" | "scheduling" | "exams" | "commercial" | "return" | "weight_loss" | "campaign";

export interface Session {
  session_id: string;
  patient_name: string | null;
  patient_phone: string;
  current_agent: AgentType;
  status: "active" | "completed";
  last_message_preview: string | null;
  last_activity_at: string;
  started_at: string;
  minutes_since_last_message: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  agent_id: string;
  message_type: string;
  created_at: string;
}

export type LeadStatus = "qualified" | "disqualified";

export const SPECIALTIES = [
  { key: "clinica_geral", label: "Clínica Geral" },
  { key: "cardiologia", label: "Cardiologia" },
  { key: "psiquiatria", label: "Psiquiatria" },
  { key: "endocrinologia", label: "Endocrinologia" },
  { key: "ginecologia", label: "Ginecologia" },
  { key: "dermatologia", label: "Dermatologia" },
  { key: "otorrinolaringologia", label: "Otorrinolaringologia" },
] as const;

export type SpecialtyKey = (typeof SPECIALTIES)[number]["key"];

export interface Lead {
  patient_name: string;
  patient_phone: string;
  specialty: string | null;
  status: LeadStatus;
  disqualification_reason: string | null;
  scheduled_date: string | null;
  scheduled_time: string | null;
  professional_name: string | null;
  appointment_id: string | null;
  created_at: string;
  session_id: string;
}

export interface LeadsSummary {
  qualified: number;
  disqualified: number;
  by_specialty: Record<string, { qualified: number; disqualified: number }>;
}

export type PriorityLeadStatus = "aguardando" | "em_contato" | "agendado" | "descartado";

export interface PriorityLead {
  id: string;
  patient_id: string | null;
  session_id: string | null;
  patient_name: string | null;
  patient_phone: string;
  interest: string;
  convenio: string | null;
  specialty: string | null;
  source_agent: string | null;
  campaign_name: string | null;
  caneta_preferida: string | null;
  periodo_preferido: string | null;
  professional_id: number | null;
  professional_name: string | null;
  notes: string | null;
  summary: string | null;
  action_label: string | null;
  priority_type: string;
  priority_score: number;
  metadata: Record<string, unknown> | string | null;
  status: PriorityLeadStatus;
  handled_by: string | null;
  handled_at: string | null;
  appointment_id: string | null;
  created_at: string;
  updated_at: string;
  hours_waiting: number | null;
}

export interface PriorityLeadsSummary {
  aguardando: number;
  em_contato: number;
  agendado: number;
  descartado: number;
  total: number;
}
