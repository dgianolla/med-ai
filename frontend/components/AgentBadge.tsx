import { AgentType } from "@/types";

const AGENT_CONFIG: Record<AgentType, { label: string; color: string }> = {
  triage:     { label: "Triagem",      color: "bg-gray-100 text-gray-700 border-gray-300" },
  scheduling: { label: "Agendamento",  color: "bg-teal-100 text-teal-700 border-teal-300" },
  exams:      { label: "Exames",       color: "bg-purple-100 text-purple-700 border-purple-300" },
  commercial: { label: "Comercial",    color: "bg-green-100 text-green-700 border-green-300" },
  return:     { label: "Retorno",      color: "bg-orange-100 text-orange-700 border-orange-300" },
};

export function AgentBadge({ agent }: { agent: AgentType }) {
  const config = AGENT_CONFIG[agent] ?? { label: agent, color: "bg-gray-100 text-gray-600 border-gray-300" };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${config.color}`}>
      {config.label}
    </span>
  );
}
