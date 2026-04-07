"use client";

import { useState } from "react";
import { Session, Message } from "@/types";
import { AgentBadge } from "./AgentBadge";

function formatTime(minutes: number): string {
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${Math.floor(minutes)}min atrás`;
  const h = Math.floor(minutes / 60);
  return `${h}h atrás`;
}

function formatPhone(phone: string | null | undefined): string {
  if (!phone) return "";
  // 5511988579353 → (11) 98857-9353
  const digits = String(phone).replace(/\D/g, "").replace(/^55/, "");
  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }
  return phone;
}

async function fetchMessages(sessionId: string): Promise<Message[]> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  const res = await fetch(`${apiUrl}/api/dashboard/sessions/${sessionId}/messages`);
  const data = await res.json();
  return data.messages ?? [];
}

export function SessionCard({ session }: { session: Session }) {
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleExpand() {
    if (!expanded && messages.length === 0) {
      setLoading(true);
      const msgs = await fetchMessages(session.session_id);
      setMessages(msgs);
      setLoading(false);
    }
    setExpanded((v) => !v);
  }

  const isUrgent = session.minutes_since_last_message > 10;

  return (
    <div className={`bg-white rounded-xl border shadow-sm transition-all ${
      isUrgent ? "border-red-200" : "border-gray-200"
    }`}>
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-900 truncate">
              {session.patient_name ?? "Paciente desconhecido"}
            </p>
            <p className="text-sm text-gray-500">{formatPhone(session.patient_phone)}</p>
          </div>
          <AgentBadge agent={session.current_agent} />
        </div>

        {/* Preview da última mensagem */}
        {session.last_message_preview && (
          <p className="mt-2 text-sm text-gray-600 line-clamp-2 italic">
            &ldquo;{session.last_message_preview}&rdquo;
          </p>
        )}

        {/* Footer */}
        <div className="mt-3 flex items-center justify-between">
          <span className={`text-xs ${isUrgent ? "text-red-500 font-medium" : "text-gray-400"}`}>
            ⏱ {formatTime(session.minutes_since_last_message)}
          </span>
          <button
            onClick={handleExpand}
            className="text-xs text-green-600 hover:text-green-800 font-medium"
          >
            {expanded ? "Fechar" : "Ver conversa"}
          </button>
        </div>
      </div>

      {/* Conversa expandida */}
      {expanded && (
        <div className="border-t border-gray-100 p-3 max-h-72 overflow-y-auto bg-gray-50 rounded-b-xl space-y-2">
          {loading && (
            <p className="text-center text-xs text-gray-400 py-4">Carregando...</p>
          )}
          {!loading && messages.length === 0 && (
            <p className="text-center text-xs text-gray-400 py-4">Sem mensagens registradas.</p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                  msg.role === "user"
                    ? "bg-white border border-gray-200 text-gray-700"
                    : "bg-green-600 text-white"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.role === "assistant" && (
                  <p className="mt-1 opacity-70 text-[10px]">{msg.agent_id}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
