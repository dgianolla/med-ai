"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useToast } from "@/components/Toast";
import { TableSkeleton } from "@/components/Skeletons";
import { API_URL } from "@/lib/config";
import { formatAppointmentTime } from "@/lib/format";

type Confirmation = {
  appointment_id: string;
  patient_name: string;
  patient_phone: string;
  appointment_time: string;
  professional_name: string;
  status: "not_started" | "pending" | "sent" | "failed" | "confirmed" | "canceled";
};

export default function ConfirmationsPage() {
  const { success, error, info } = useToast();
  const [delay, setDelay] = useState(10);
  const [targetDate, setTargetDate] = useState("");
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const fetchPreview = useCallback(async (date: string) => {
    if (!date) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/schedules/preview?date=${date}`);
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Erro ${res.status}: falha ao buscar agenda`);
      }
      const data = await res.json();
      const schedules = data.schedules || [];
      setConfirmations(schedules);
      if (schedules.length === 0) {
        info("Nenhum agendamento encontrado para esta data.");
      }
    } catch (e: any) {
      console.error("[PREVIEW] Erro:", e);
      error(e.message || "Erro ao carregar agenda");
      setConfirmations([]);
    } finally {
      setLoading(false);
    }
  }, [error, info]);

  // Initialize with tomorrow for default
  useEffect(() => {
    const tmr = new Date();
    tmr.setDate(tmr.getDate() + 1);
    const defaultDate = tmr.toISOString().split("T")[0];
    setTargetDate(defaultDate);
    // Auto-fetch a agenda quando a página carrega
    fetchPreview(defaultDate);
  }, [fetchPreview]);

  useEffect(() => {
    // Poll every 5s to see dispatch status updates ONLY if triggering
    const id = setInterval(() => {
      if (targetDate && triggering) fetchPreview(targetDate);
    }, 5000);
    return () => clearInterval(id);
  }, [targetDate, triggering]);

  const handleStart = async () => {
    setTriggering(true);
    try {
      const res = await fetch(`${API_URL}/api/schedules/trigger-confirmations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delay_seconds: delay, target_date: targetDate }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || "Falha ao iniciar disparo");
      }
      const data = await res.json();
      success(`Disparo iniciado! ${data.total_schedules_found} agendamento(s) encontrado(s).`);
      // Aguarda um pouco e busca o preview atualizado
      setTimeout(() => fetchPreview(targetDate), 2000);
    } catch (e: any) {
      console.error("[TRIGGER] Erro:", e);
      error(e.message || "Erro de conexão ao iniciar disparo");
    } finally {
      setTriggering(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      not_started: "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700",
      pending: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200",
      sent: "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200",
      confirmed: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200",
      canceled: "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200",
      failed: "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200",
    };

    const labels: Record<string, string> = {
      not_started: "Não Iniciado",
      pending: "Na Fila (Aguardando)",
      sent: "Enviado (Aguardando)",
      confirmed: "Confirmado",
      canceled: "Cancelado",
      failed: "Falha no Envio",
    };

    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[status] ?? styles.not_started}`}>
        {labels[status] ?? status}
      </span>
    );
  };

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <img src="/logo.png" alt="Atend Já" className="h-8 w-auto object-contain" />
              <div>
                <p className="font-semibold text-gray-900 dark:text-gray-100 text-sm leading-none">Atend Já</p>
              </div>
            </div>

            <nav className="flex gap-4 pt-1">
              <Link href="/" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Atendimentos</Link>
              <Link href="/leads" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Leads</Link>
              <Link href="/leads/encaixe" className="text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors py-4">Encaixe</Link>
              <Link href="/confirmacoes" className="text-sm font-medium text-green-600 dark:text-green-500 border-b-2 border-green-600 dark:border-green-500 py-4">Confirmações</Link>
            </nav>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Configuração */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div className="flex gap-4 flex-1 flex-wrap">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Data da Agenda</label>
                <input
                  type="date"
                  value={targetDate}
                  onChange={e => setTargetDate(e.target.value)}
                  className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 text-sm max-w-[150px] w-full focus:outline-none focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div>
                <button
                  onClick={() => fetchPreview(targetDate)}
                  disabled={loading}
                  className="bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 border border-gray-300 dark:border-gray-600 font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50 h-[38px]"
                >
                  {loading ? "Buscando..." : "Buscar Agenda"}
                </button>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Delay (Segundos)</label>
                <input
                  type="number"
                  min="1"
                  value={delay}
                  onChange={e => setDelay(Number(e.target.value) || 1)}
                  className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 text-sm max-w-[120px] w-full focus:outline-none focus:ring-2 focus:ring-green-500"
                  title="Segundos entre o envio de cada mensagem"
                />
              </div>
            </div>
            <button
              onClick={handleStart}
              disabled={triggering || confirmations.length === 0}
              className="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {triggering ? "Iniciando..." : "➔ Iniciar Disparos"}
            </button>
          </div>
        </div>

        {/* Tabela */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Paciente</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Horário</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Profissional</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
              </tr>
            </thead>
            {loading ? (
              <TableSkeleton rows={5} />
            ) : (
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {confirmations.length === 0 && !loading && (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                      Nenhum agendamento encontrado para esta data.
                    </td>
                  </tr>
                )}
                {confirmations.map(c => (
                  <tr key={c.appointment_id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{c.patient_name}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                      {formatAppointmentTime(c.appointment_time)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">{c.professional_name}</td>
                    <td className="px-6 py-4 whitespace-nowrap">{getStatusBadge(c.status)}</td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
      </div>
    </main>
  );
}
