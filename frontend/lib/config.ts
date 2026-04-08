/**
 * Configuração centralizada da API
 * Resolve inconsistência de portas entre componentes
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Intervalos de polling (em milissegundos)
 */
export const POLLING = {
  SESSIONS: 2 * 60 * 1000,      // 2 minutos
  CONFIRMATIONS: 5 * 1000,       // 5 segundos
} as const;

/**
 * Timeout de urgência para sessões (em milissegundos)
 */
export const SESSION_URGENCY_THRESHOLD = 10 * 60 * 1000; // 10 minutos
