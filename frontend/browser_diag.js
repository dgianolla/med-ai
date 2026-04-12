// Script de diagnostico do FRONTEND - Rodar no browser DevTools (F12 > Console)
// OU no container frontend via: node /app/browser_diag.js

console.log("=".repeat(70));
console.log("  DIAGNOSTICO FRONTEND - CONEXAO COM BACKEND");
console.log("=".repeat(70));

// 1. Qual URL esta sendo usada?
const API_URL = process?.env?.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
console.log("\n[1] API_URL configurada:", API_URL);

// 2. Testar backend
async function testBackend() {
  console.log("\n[2] Testando conexao com backend...");
  
  // 2a. Root
  try {
    const root = await fetch(API_URL + "/", { method: "GET", signal: AbortSignal.timeout(5000) });
    console.log("  GET / =>", root.status, await root.text().then(t => t.substring(0, 100)));
  } catch(e) {
    console.log("  GET / => ERRO:", e.message);
  }
  
  // 2b. Health
  try {
    const health = await fetch(API_URL + "/health", { method: "GET", signal: AbortSignal.timeout(5000) });
    console.log("  GET /health =>", health.status, await health.text().then(t => t.substring(0, 100)));
  } catch(e) {
    console.log("  GET /health => ERRO:", e.message);
  }
  
  // 2c. Preview
  console.log("\n[3] Testando /api/schedules/preview?date=2026-04-13:");
  try {
    const preview = await fetch(API_URL + "/api/schedules/preview?date=2026-04-13", { 
      method: "GET", 
      signal: AbortSignal.timeout(10000) 
    });
    console.log("  STATUS:", preview.status);
    if (!preview.ok) {
      const text = await preview.text();
      console.log("  BODY:", text.substring(0, 300));
    } else {
      const data = await preview.json();
      console.log("  SCHEDULES:", data.schedules?.length || 0);
      if (data.schedules?.length > 0) {
        const s = data.schedules[0];
        console.log("  EXEMPLO:", s.patient_name, "|", s.appointment_time, "|", s.patient_phone);
      }
    }
  } catch(e) {
    console.log("  ERRO:", e.message);
    console.log("  DICA: Se for 'Failed to fetch', verifique:");
    console.log("    - CORS no backend (deve permitir a origem do frontend)");
    console.log("    - HTTPS/HTTPS mismatch");
    console.log("    - Backend acessivel externamente (nao so internamente no Docker)");
  }
}

testBackend();

console.log("\n" + "=".repeat(70));
console.log("  (Resultados aparecerao acima em async)");
console.log("=".repeat(70));
