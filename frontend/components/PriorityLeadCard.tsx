"use client";

import { useState } from "react";
import { PriorityLead, PriorityLeadStatus } from "@/types";
import { formatPhone } from "@/lib/format";
import { API_URL } from "@/lib/config";

const STATUS_LABEL: Record<PriorityLeadStatus, string> = {
  aguardando: "Aguardando",
  em_contato: "Em contato",
  agendado: "Agendado",
  descartado: "Descartado",
};

const STATUS_STYLE: Record<PriorityLeadStatus, string> = {
  aguardando: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400",
  em_contato: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400",
  agendado: "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400",
  descartado: "bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300",
};

function urgencyClass(hours: number | null, status: PriorityLeadStatus): string {
  if (status !== "aguardando" || hours == null) return "border-gray-200 dark:border-gray-700";
  if (hours >= 24) return "border-red-300 dark:border-red-700 ring-1 ring-red-200 dark:ring-red-900/40";
  if (hours >= 12) return "border-amber-300 dark:border-amber-700";
  return "border-green-200 dark:border-green-800";
}

function formatWaiting(hours: number | null): string {
  if (hours == null) return "—";
  if (hours < 1) return `${Math.round(hours * 60)}min`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${Math.floor(hours / 24)}d ${Math.round(hours % 24)}h`;
}

function canetaLabel(c: string | null): string {
  if (!c) return "Indefinido";
  if (c === "ozempic") return "Ozempic";
  if (c === "mounjaro") return "Mounjaro";
  return c;
}

export function PriorityLeadCard({
  lead,
  onUpdated,
}: {
  lead: PriorityLead;
  onUpdated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function updateStatus(next: PriorityLeadStatus) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/dashboard/priority-leads/${lead.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border shadow-sm transition-all ${urgencyClass(lead.hours_waiting, lead.status)}`}>
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {lead.patient_name || "Paciente desconhecido"}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">{formatPhone(lead.patient_phone)}</p>
          </div>

          <span className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-full ${STATUS_STYLE[lead.status]}`}>
            {STATUS_LABEL[lead.status]}
          </span>
        </div>

        {/* Caneta de interesse */}
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">💉</span>
          <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
            {canetaLabel(lead.caneta_preferida)}
          </span>
        </div>

        {/* Tempo aguardando */}
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">⏱</span>
          <span className={`text-sm font-medium ${
            lead.status === "aguardando" && lead.hours_waiting != null && lead.hours_waiting >= 24
              ? "text-red-600 dark:text-red-400"
              : "text-gray-600 dark:text-gray-300"
          }`}>
            {lead.status === "aguardando" ? `Aguardando há ${formatWaiting(lead.hours_waiting)}` : `Criado há ${formatWaiting(lead.hours_waiting)}`}
          </span>
        </div>

        {/* Notes */}
        {lead.notes && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-3 whitespace-pre-wrap">
              {lead.notes}
            </p>
          </div>
        )}

        {/* Ações */}
        {(lead.status === "aguardando" || lead.status === "em_contato") && (
          <div className="mt-4 flex flex-wrap gap-2">
            {lead.status === "aguardando" && (
              <button
                disabled={busy}
                onClick={() => updateStatus("em_contato")}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                Marcar em contato
              </button>
            )}
            <button
              disabled={busy}
              onClick={() => updateStatus("agendado")}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              Marcar agendado
            </button>
            <button
              disabled={busy}
              onClick={() => updateStatus("descartado")}
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
            >
              Descartar
            </button>
          </div>
        )}

        {error && (
          <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>
        )}
      </div>
    </div>
  );
}
