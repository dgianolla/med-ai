export type AgentType = "triage" | "scheduling" | "exams" | "commercial" | "return";

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
