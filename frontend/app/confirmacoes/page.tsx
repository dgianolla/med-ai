"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

type Confirmation = {
  appointment_id: string;
  patient_name: string;
  patient_phone: string;
  appointment_time: string;
  professional_name: string;
  status: "not_started" | "pending" | "sent" | "failed" | "confirmed" | "canceled";
};

export default function ConfirmationsPage() {
  const [delay, setDelay] = useState(10);
  const [targetDate, setTargetDate] = useState("");
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);

  // Initialize with tomorrow for default
  useEffect(() => {
    const tmr = new Date();
    tmr.setDate(tmr.getDate() + 1);
    setTargetDate(tmr.toISOString().split("T")[0]);
  }, []);

  const fetchPreview = async (date: string) => {
    if (!date) return;
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/schedules/preview?date=${date}`);
      const data = await res.json();
      setConfirmations(data.schedules || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/schedules/trigger-confirmations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delay_seconds: delay, target_date: targetDate }),
      });
      if (res.ok) {
        alert("Disparo de confirmações em lote iniciado com sucesso!");
        fetchPreview(targetDate);
      } else {
        alert("Falha ao iniciar disparo");
      }
    } catch (e) {
      console.error(e);
    }
    setTriggering(false);
  };

  const getStatusBadge = (status: string) => {
    switch(status) {
      case "not_started": return <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded-full text-xs font-medium border border-gray-200">Não Iniciado</span>;
      case "pending": return <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs font-medium">Na Fila (Aguardando Delay)</span>;
      case "sent": return <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">Enviado (Aguardando)</span>;
      case "confirmed": return <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">Confirmado</span>;
      case "canceled": return <span className="px-2 py-1 bg-red-100 text-red-800 rounded-full text-xs font-medium">Cancelado</span>;
      case "failed": return <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded-full text-xs font-medium">Falha no Envio</span>;
      default: return null;
    }
  };

  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <img src="/logo.png" alt="Atend Já" className="h-8 w-auto object-contain" />
              <div>
                <p className="font-semibold text-gray-900 text-sm leading-none">Atend Já</p>
              </div>
            </div>
            
            <nav className="flex gap-4 pt-1">
              <Link href="/" className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors py-4">Atendimentos</Link>
              <Link href="/confirmacoes" className="text-sm font-medium text-green-600 border-b-2 border-green-600 py-4">Confirmações</Link>
            </nav>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-end justify-between gap-4">
            <div className="flex gap-4 flex-1">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data da Agenda</label>
                <input 
                  type="date" 
                  value={targetDate}
                  onChange={e => setTargetDate(e.target.value)}
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm max-w-[150px] w-full block"
                />
              </div>
              <div>
                <button 
                  onClick={() => fetchPreview(targetDate)}
                  disabled={loading}
                  className="bg-gray-100 hover:bg-gray-200 text-gray-800 border border-gray-300 font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50 h-[38px]"
                >
                  {loading ? "Buscando..." : "Buscar Agenda"}
                </button>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Delay (Segundos)</label>
                <input 
                  type="number" 
                  min="1"
                  value={delay}
                  onChange={e => setDelay(Number(e.target.value) || 1)}
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm max-w-[120px] w-full"
                  title="Segundos entre o envio de cada mensagem"
                />
              </div>
            </div>
            <button 
              onClick={handleStart}
              disabled={triggering}
              className="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {triggering ? "Iniciando..." : "➔ Iniciar Disparos"}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Paciente</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Horário</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Profissional</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {confirmations.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">
                    {loading ? "Carregando..." : "Nenhum disparo registrado para esta data ainda."}
                  </td>
                </tr>
              )}
              {confirmations.map(c => (
                <tr key={c.appointment_id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{c.patient_name}</div>
                    <div className="text-sm text-gray-500">{c.patient_phone}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{c.appointment_time}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{c.professional_name}</td>
                  <td className="px-6 py-4 whitespace-nowrap">{getStatusBadge(c.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
