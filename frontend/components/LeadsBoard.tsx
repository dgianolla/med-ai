"use client";

import { useEffect, useState, useCallback } from "react";
import { Lead, LeadsSummary, LeadStatus, SPECIALTIES, SpecialtyKey } from "@/types";
import { LeadCard } from "./LeadCard";
import { LeadsSummaryCard } from "./LeadsSummary";
import { API_URL, POLLING } from "@/lib/config";

interface LeadsResponse {
  leads: Lead[];
  summary: LeadsSummary;
}

async function fetchLeads(
  status?: LeadStatus,
  specialty?: string,
): Promise<LeadsResponse> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (specialty) params.set("specialty", specialty);

  const res = await fetch(`${API_URL}/api/dashboard/leads?${params.toString()}`, {
    cache: "no-store",
  });
  const data = await res.json();
  return { leads: data.leads ?? [], summary: data.summary ?? { qualified: 0, disqualified: 0, by_specialty: {} } };
}

function specialtyLabel(key: string): string {
  const found = SPECIALTIES.find((s) => s.key === key);
  return found?.label ?? key;
}

export function LeadsBoard() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [summary, setSummary] = useState<LeadsSummary | null>(null);
  const [filterStatus, setFilterStatus] = useState<LeadStatus | "all">("all");
  const [filterSpecialty, setFilterSpecialty] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchLeads(
        filterStatus === "all" ? undefined : filterStatus,
        filterSpecialty || undefined,
      );
      setLeads(data.leads);
      setSummary(data.summary);
      setLastUpdated(new Date());
    } catch (err) {
      console.error("Erro ao buscar leads:", err);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterSpecialty]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLLING.LEADS);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="space-y-6">
      {/* Summary */}
      <LeadsSummaryCard summary={summary} />

      {/* Filtros */}
      <div className="flex flex-wrap gap-3">
        {/* Tabs de status */}
        <div className="flex gap-2">
          {(["all", "qualified", "disqualified"] as const).map((s) => {
            const label = s === "all" ? "Todos" : s === "qualified" ? "Qualificados" : "Desqualificados";
            const active = filterStatus === s;
            return (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  active
                    ? s === "qualified"
                      ? "bg-green-600 text-white shadow-sm"
                      : s === "disqualified"
                        ? "bg-red-600 text-white shadow-sm"
                        : "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-sm"
                    : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Dropdown especialidade */}
        <select
          value={filterSpecialty}
          onChange={(e) => setFilterSpecialty(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          <option value="">Todas especialidades</option>
          {SPECIALTIES.map((s) => (
            <option key={s.key} value={s.key}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Grid de leads */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
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
              <p className="text-4xl mb-3">📋</p>
              <p className="text-sm">
                {filterStatus !== "all" || filterSpecialty
                  ? "Nenhum lead encontrado para estes filtros."
                  : "Nenhum lead registrado ainda."}
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {leads.map((lead) => (
              <LeadCard key={`${lead.patient_phone}-${lead.appointment_id}`} lead={lead} />
            ))}
          </div>
        </>
      )}

      {/* Rodapé */}
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
