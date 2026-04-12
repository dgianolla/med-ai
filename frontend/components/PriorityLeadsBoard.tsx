"use client";

import { useEffect, useState, useCallback } from "react";
import { PriorityLead, PriorityLeadsSummary, PriorityLeadStatus } from "@/types";
import { PriorityLeadCard } from "./PriorityLeadCard";
import { API_URL, POLLING } from "@/lib/config";

interface ApiResponse {
  leads: PriorityLead[];
  summary: PriorityLeadsSummary;
}

const TABS: Array<{ key: PriorityLeadStatus | "all"; label: string }> = [
  { key: "all", label: "Todos" },
  { key: "aguardando", label: "Aguardando" },
  { key: "em_contato", label: "Em contato" },
  { key: "agendado", label: "Agendados" },
  { key: "descartado", label: "Descartados" },
];

async function fetchPriorityLeads(status?: PriorityLeadStatus): Promise<ApiResponse> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_URL}/api/dashboard/priority-leads?${params.toString()}`, {
    cache: "no-store",
  });
  const data = await res.json();
  return {
    leads: data.leads ?? [],
    summary: data.summary ?? { aguardando: 0, em_contato: 0, agendado: 0, descartado: 0, total: 0 },
  };
}

export function PriorityLeadsBoard() {
  const [leads, setLeads] = useState<PriorityLead[]>([]);
  const [summary, setSummary] = useState<PriorityLeadsSummary | null>(null);
  const [filter, setFilter] = useState<PriorityLeadStatus | "all">("aguardando");
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchPriorityLeads(filter === "all" ? undefined : filter);
      setLeads(data.leads);
      setSummary(data.summary);
      setLastUpdated(new Date());
    } catch (err) {
      console.error("Erro ao buscar priority leads:", err);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLLING.LEADS);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <SummaryCard label="Aguardando" value={summary.aguardando} tone="amber" />
          <SummaryCard label="Em contato" value={summary.em_contato} tone="blue" />
          <SummaryCard label="Agendados" value={summary.agendado} tone="green" />
          <SummaryCard label="Descartados" value={summary.descartado} tone="gray" />
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const active = filter === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setFilter(t.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                active
                  ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-sm"
                  : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 animate-pulse">
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mb-4"></div>
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {leads.length === 0 && (
            <div className="text-center py-16 text-gray-400 dark:text-gray-500">
              <p className="text-4xl mb-3">💉</p>
              <p className="text-sm">Nenhum lead nesta categoria.</p>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {leads.map((lead) => (
              <PriorityLeadCard key={lead.id} lead={lead} onUpdated={refresh} />
            ))}
          </div>
        </>
      )}

      {lastUpdated && (
        <p className="text-center text-xs text-gray-400 dark:text-gray-500">
          Atualizado às {lastUpdated.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
          <button
            onClick={refresh}
            className="ml-2 text-green-600 dark:text-green-500 hover:text-green-800 dark:hover:text-green-400 underline"
          >
            atualizar agora
          </button>
        </p>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "amber" | "blue" | "green" | "gray";
}) {
  const toneClass = {
    amber: "text-amber-600 dark:text-amber-400",
    blue: "text-blue-600 dark:text-blue-400",
    green: "text-green-600 dark:text-green-400",
    gray: "text-gray-600 dark:text-gray-400",
  }[tone];

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  );
}
