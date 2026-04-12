import { LeadsSummary, SPECIALTIES } from "@/types";

interface LeadsSummaryProps {
  summary: LeadsSummary | null;
}

function specialtyLabel(key: string): string {
  const found = SPECIALTIES.find((s) => s.key === key);
  return found?.label ?? key;
}

export function LeadsSummaryCard({ summary }: LeadsSummaryProps) {
  if (!summary) return null;

  const total = summary.qualified + summary.disqualified;
  const conversionRate = total > 0
    ? Math.round((summary.qualified / total) * 100)
    : 0;

  return (
    <div className="space-y-4">
      {/* Métricas principais */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium">Qualificados</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-500 mt-1">{summary.qualified}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium">Desqualificados</p>
          <p className="text-3xl font-bold text-red-600 dark:text-red-500 mt-1">{summary.disqualified}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium">Taxa de conversão</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-500 mt-1">{conversionRate}%</p>
        </div>
      </div>

      {/* Por especialidade */}
      {Object.keys(summary.by_specialty).length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide font-medium mb-3">Por especialidade</p>
          <div className="space-y-2">
            {Object.entries(summary.by_specialty)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([spec, counts]) => (
                <div key={spec} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700 dark:text-gray-300 font-medium">{specialtyLabel(spec)}</span>
                  <div className="flex gap-3">
                    <span className="text-green-600 dark:text-green-500 font-semibold">{counts.qualified} qual.</span>
                    <span className="text-red-600 dark:text-red-500 font-semibold">{counts.disqualified} desq.</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
