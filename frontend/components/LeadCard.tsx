import { Lead, SPECIALTIES } from "@/types";
import { formatPhone } from "@/lib/format";

function specialtyLabel(key: string | null): string {
  if (!key) return "Sem especialidade";
  const found = SPECIALTIES.find((s) => s.key === key);
  return found?.label ?? key;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export function LeadCard({ lead }: { lead: Lead }) {
  const isQualified = lead.status === "qualified";

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border shadow-sm transition-all ${
      isQualified
        ? "border-green-200 dark:border-green-800"
        : "border-red-200 dark:border-red-800"
    }`}>
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {lead.patient_name || "Paciente desconhecido"}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">{formatPhone(lead.patient_phone)}</p>
          </div>

          {/* Status badge */}
          <span className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-full ${
            isQualified
              ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400"
              : "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400"
          }`}>
            {isQualified ? "Qualificado" : "Desqualificado"}
          </span>
        </div>

        {/* Especialidade */}
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">🩺</span>
          <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
            {specialtyLabel(lead.specialty)}
          </span>
        </div>

        {/* Data agendamento (se qualificado) */}
        {isQualified && lead.scheduled_date && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">📅</span>
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {formatDate(lead.scheduled_date)}
              {lead.scheduled_time && ` às ${lead.scheduled_time}`}
            </span>
          </div>
        )}

        {/* Profissional (se qualificado) */}
        {isQualified && lead.professional_name && (
          <div className="mt-1 flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">👨‍⚕️</span>
            <span className="text-sm text-gray-600 dark:text-gray-300">{lead.professional_name}</span>
          </div>
        )}

        {/* Motivo desqualificação */}
        {!isQualified && lead.disqualification_reason && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <p className="text-xs text-red-600 dark:text-red-400 font-medium">
              ✖ Motivo: {lead.disqualification_reason === "cancelled" ? "Cancelou/Desistiu" : lead.disqualification_reason}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
