import { AgentType } from "@/types";

const AGENT_CONFIG: Record<AgentType, { label: string; color: string }> = {
  triage:     { label: "Triagem",      color: "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600" },
  scheduling: { label: "Agendamento",  color: "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 border-teal-300 dark:border-teal-700" },
  exams:      { label: "Exames",       color: "bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700" },
  commercial: { label: "Comercial",    color: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700" },
  return:     { label: "Retorno",      color: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700" },
};

export function AgentBadge({ agent }: { agent: AgentType }) {
  const config = AGENT_CONFIG[agent] ?? { label: agent, color: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-600" };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${config.color}`}>
      {config.label}
    </span>
  );
}
