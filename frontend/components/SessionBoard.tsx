"use client";

import { useEffect, useState, useCallback } from "react";
import { Session, AgentType } from "@/types";
import { SessionCard } from "./SessionCard";
import { AgentBadge } from "./AgentBadge";
import { SessionBoardSkeleton } from "./Skeletons";
import { API_URL, POLLING } from "@/lib/config";
import { formatTime } from "@/lib/format";

const COLUMNS: { agent: AgentType | "all"; label: string }[] = [
  { agent: "all",        label: "Todos" },
  { agent: "triage",     label: "Triagem" },
  { agent: "scheduling", label: "Agendamento" },
  { agent: "exams",      label: "Exames" },
  { agent: "commercial", label: "Comercial" },
  { agent: "return",     label: "Retorno" },
];

async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${API_URL}/api/dashboard/sessions`, { cache: "no-store" });
  const data = await res.json();
  return data.sessions ?? [];
}

export function SessionBoard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState<AgentType | "all">("all");
  const [search, setSearch] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error("Erro ao buscar sessões:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLLING.SESSIONS);
    return () => clearInterval(interval);
  }, [refresh]);

  // Filtra por agente e busca
  const filtered = sessions.filter((s) => {
    const matchesAgent = filter === "all" || s.current_agent === filter;
    const matchesSearch = search === "" ||
      s.patient_name?.toLowerCase().includes(search.toLowerCase()) ||
      s.patient_phone.includes(search);
    return matchesAgent && matchesSearch;
  });

  const counts = sessions.reduce<Record<string, number>>((acc, s) => {
    acc[s.current_agent] = (acc[s.current_agent] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Busca */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <input
            type="text"
            placeholder="Buscar por nome ou telefone..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full px-4 py-2.5 pl-10 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
          />
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Filtros por agente */}
      <div className="flex flex-wrap gap-2">
        {COLUMNS.map(({ agent, label }) => {
          const count = agent === "all" ? sessions.length : (counts[agent] ?? 0);
          const active = filter === agent;
          return (
            <button
              key={agent}
              onClick={() => setFilter(agent)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                active
                  ? "bg-green-600 text-white shadow-sm"
                  : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-green-300 dark:hover:border-green-700"
              }`}
            >
              {label}
              <span className={`text-xs rounded-full px-1.5 py-0.5 ${
                active ? "bg-green-500 text-white" : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Grid de cards */}
      {loading ? (
        <SessionBoardSkeleton />
      ) : (
        <>
          {filtered.length === 0 && (
            <div className="text-center py-16 text-gray-400 dark:text-gray-500">
              <p className="text-4xl mb-3">🩺</p>
              <p className="text-sm">
                {sessions.length === 0
                  ? "Nenhuma sessão ativa no momento."
                  : "Nenhuma sessão encontrada para este filtro."}
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((session) => (
              <SessionCard key={session.session_id} session={session} />
            ))}
          </div>
        </>
      )}

      {/* Rodapé */}
      {lastUpdated && (
        <p className="text-center text-xs text-gray-400 dark:text-gray-500">
          Atualizado às {formatTime(lastUpdated)} · próxima atualização em 2 min
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
