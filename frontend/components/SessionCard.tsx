"use client";

import { useState } from "react";
import { Session, Message } from "@/types";
import { AgentBadge } from "./AgentBadge";
import { API_URL } from "@/lib/config";
import { formatPhone, formatRelativeTime, minutesAgo } from "@/lib/format";

async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_URL}/api/dashboard/sessions/${sessionId}/messages`);
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

  const minutes = minutesAgo(new Date(session.last_activity_at));
  const isUrgent = minutes > 10;

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border shadow-sm transition-all ${
      isUrgent
        ? "border-red-300 dark:border-red-700 ring-1 ring-red-100 dark:ring-red-900"
        : "border-gray-200 dark:border-gray-700"
    }`}>
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {session.patient_name ?? "Paciente desconhecido"}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">{formatPhone(session.patient_phone)}</p>
          </div>
          <AgentBadge agent={session.current_agent} />
        </div>

        {/* Preview da última mensagem */}
        {session.last_message_preview && (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2 italic">
            &ldquo;{session.last_message_preview}&rdquo;
          </p>
        )}

        {/* Footer */}
        <div className="mt-3 flex items-center justify-between">
          <span className={`text-xs flex items-center gap-1 ${
            isUrgent ? "text-red-600 dark:text-red-400 font-medium" : "text-gray-400 dark:text-gray-500"
          }`}>
            {isUrgent && <span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse"></span>}
            ⏱ {formatRelativeTime(new Date(session.last_activity_at))}
          </span>
          <button
            onClick={handleExpand}
            className="text-xs text-green-600 dark:text-green-500 hover:text-green-800 dark:hover:text-green-400 font-medium transition-colors"
          >
            {expanded ? "Fechar" : "Ver conversa"}
          </button>
        </div>
      </div>

      {/* Conversa expandida */}
      {expanded && (
        <div className="border-t border-gray-100 dark:border-gray-700 p-3 max-h-72 overflow-y-auto bg-gray-50 dark:bg-gray-900/50 rounded-b-xl space-y-2">
          {loading && (
            <div className="space-y-2 py-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}>
                  <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-lg w-3/4 animate-pulse"></div>
                </div>
              ))}
            </div>
          )}
          {!loading && messages.length === 0 && (
            <p className="text-center text-xs text-gray-400 dark:text-gray-500 py-4">Sem mensagens registradas.</p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-start" : "justify-end"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                  msg.role === "user"
                    ? "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200"
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
