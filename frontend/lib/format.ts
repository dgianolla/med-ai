/**
 * Utilitários de formatação
 */

/**
 * Formata número de telefone brasileiro
 * Ex: +5515999999999 → (15) 99999-9999
 */
export function formatPhone(phone: string): string {
  const cleaned = phone.replace(/\D/g, "");
  // Remove country code if present
  const digits = cleaned.length > 11 ? cleaned.slice(-11) : cleaned;

  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  }
  return phone; // Retorna original se não conseguir formatar
}

/**
 * Formata data/hora para exibição amigável
 * Ex: "Hoje às 14:30", "Ontem às 09:15", "07/04 às 16:45"
 */
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return "Agora mesmo";
  if (minutes < 60) return `${minutes}min atrás`;
  if (hours < 24) return `${hours}h atrás`;
  if (days === 1) return `Ontem às ${date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;

  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) +
    " às " +
    date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Formata horário de consulta
 * Ex: "2024-04-07T14:30:00" → "07/04/2024 às 14:30"
 */
export function formatAppointmentTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }) + " às " + date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Formata hora curta
 * Ex: "14:30"
 */
export function formatTime(date: Date): string {
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Calcula diferença em minutos entre agora e uma data
 */
export function minutesAgo(date: Date): number {
  const now = new Date();
  return Math.floor((now.getTime() - date.getTime()) / 60000);
}
