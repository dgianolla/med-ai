"use client";

import { useEffect, useState, useCallback } from "react";
import { Session, AgentType } from "@/types";
import { SessionCard } from "./SessionCard";
import { AgentBadge } from "./AgentBadge";

const COLUMNS: { agent: AgentType | "all"; label: string }[] = [
  { agent: "all",        label: "Todos" },
  { agent: "scheduling", label: "Agendamento" },
  { agent: "exams",      label: "Exames" },
  { agent: "commercial", label: "Comercial" },
  { agent: "return",     label: "Retorno" },
];

const REFRESH_INTERVAL = 2 * 60 * 1000; // 2 minutos

async function fetchSessions(): Promise<Session[]> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  const res = await fetch(`${apiUrl}/api/dashboard/sessions`, { cache: "no-store" });
  const data = await res.json();
  return data.sessions ?? [];
}

export function SessionBoard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState<AgentType | "all">("all");
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
    const interval = setInterval(refresh, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  const filtered = filter === "all"
    ? sessions
    : sessions.filter((s) => s.current_agent === filter);

  const counts = sessions.reduce<Record<string, number>>((acc, s) => {
    acc[s.current_agent] = (acc[s.current_agent] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Filtros */}
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
                  : "bg-white text-gray-600 border border-gray-200 hover:border-green-300"
              }`}
            >
              {label}
              <span className={`text-xs rounded-full px-1.5 py-0.5 ${
                active ? "bg-green-500 text-white" : "bg-gray-100 text-gray-500"
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Grid de cards */}
      {loading && (
        <div className="text-center py-16 text-gray-400">Carregando sessões...</div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">🩺</p>
          <p className="text-sm">Nenhuma sessão ativa no momento.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filtered.map((session) => (
          <SessionCard key={session.session_id} session={session} />
        ))}
      </div>

      {/* Rodapé */}
      {lastUpdated && (
        <p className="text-center text-xs text-gray-400">
          Atualizado às {lastUpdated.toLocaleTimeString("pt-BR")} · próxima atualização em 2 min
          <button
            onClick={refresh}
            className="ml-2 text-green-600 hover:text-green-800 underline"
          >
            atualizar agora
          </button>
        </p>
      )}
    </div>
  );
}
