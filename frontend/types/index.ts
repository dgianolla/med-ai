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
