/**
 * Configuração centralizada da API
 * O frontend fala sempre com a mesma origem e o proxy do Next.js
 * encaminha as requisições para o backend real no servidor.
 */

export const API_URL = "";

/**
 * Intervalos de polling (em milissegundos)
 */
export const POLLING = {
  SESSIONS: 2 * 60 * 1000,      // 2 minutos
  CONFIRMATIONS: 5 * 1000,       // 5 segundos
  LEADS: 5 * 60 * 1000,          // 5 minutos
} as const;

/**
 * Timeout de urgência para sessões (em milissegundos)
 */
export const SESSION_URGENCY_THRESHOLD = 10 * 60 * 1000; // 10 minutos
