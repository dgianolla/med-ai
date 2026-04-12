// Script de diagnostico para rodar no container do frontend (Node.js)
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

console.log('='.repeat(60));
console.log('  DIAGNOSTICO DO FRONTEND (Node.js)');
console.log('='.repeat(60));

// 1. NEXT_PUBLIC_API_URL
console.log('\n[1] NEXT_PUBLIC_API_URL no ambiente:');
console.log(`  NEXT_PUBLIC_API_URL=${process.env.NEXT_PUBLIC_API_URL || 'NAO DEFINIDO'}`);

// 2. Buscar no bundle compilado o valor real (build-time)
console.log('\n[2] Buscando API_URL no codigo compilado:');
function grepDir(dir, search, limit = 5) {
    const results = [];
    try {
        const files = fs.readdirSync(dir);
        for (const file of files) {
            if (results.length >= limit) break;
            const full = path.join(dir, file);
            try {
                const stat = fs.statSync(full);
                if (stat.isDirectory()) {
                    const sub = grepDir(full, search, limit - results.length);
                    results.push(...sub);
                } else if (stat.size < 500000) {
                    const content = fs.readFileSync(full, 'utf8');
                    if (content.includes(search)) {
                        results.push(full.substring(0, 200));
                    }
                }
            } catch {}
        }
    } catch {}
    return results;
}
const found = grepDir('/app', 'NEXT_PUBLIC_API_URL');
if (found.length > 0) {
    found.forEach(f => console.log(`  ${f}`));
} else {
    console.log('  Nao encontrado (valor foi inlined no build)');
}

// 3. Testar acesso ao backend
function testUrl(url) {
    return new Promise((resolve) => {
        const client = url.startsWith('https') ? https : http;
        const req = client.get(url, { timeout: 5000 }, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                resolve({ status: res.statusCode, body: body.substring(0, 500) });
            });
        });
        req.on('error', (e) => resolve({ error: e.message }));
        req.on('timeout', () => { req.destroy(); resolve({ error: 'TIMEOUT (5s)' }); });
    });
}

async function main() {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    
    console.log('\n[3] Testando conexao com backend:');
    console.log(`  URL: ${backendUrl}`);
    
    // Test root
    const root = await testUrl(`${backendUrl}/`);
    console.log(`  GET / => ${root.error ? 'ERRO: ' + root.error : root.status + ' ' + root.body.substring(0, 100)}`);
    
    // Test health
    const health = await testUrl(`${backendUrl}/health`);
    console.log(`  GET /health => ${health.error ? 'ERRO: ' + health.error : health.status + ' ' + health.body.substring(0, 100)}`);
    
    // Test preview endpoint
    console.log(`\n[4] Testando /api/schedules/preview?date=2026-04-13:`);
    const preview = await testUrl(`${backendUrl}/api/schedules/preview?date=2026-04-13`);
    if (preview.error) {
        console.log(`  ERRO: ${preview.error}`);
    } else {
        console.log(`  STATUS: ${preview.status}`);
        try {
            const data = JSON.parse(preview.body);
            console.log(`  SCHEDULES: ${data.schedules ? data.schedules.length : 'N/A'}`);
            if (data.schedules && data.schedules.length > 0) {
                console.log(`  Primeiro: ${data.schedules[0].patient_name}`);
            }
        } catch {
            console.log(`  BODY: ${preview.body.substring(0, 200)}`);
        }
    }
    
    // 4. Portas ouvindo (aproximado)
    console.log('\n[5] Arquivos no container:');
    for (const p of ['/app/.next', '/app/server.js', '/app/package.json', '/app/.env.local']) {
        try {
            const stat = fs.statSync(p);
            console.log(`  ${p}: ${stat.isDirectory() ? 'DIR' : 'OK'} (${stat.size} bytes)`);
        } catch {
            console.log(`  ${p}: NAO EXISTE`);
        }
    }
    
    // Check server.js content for port
    console.log('\n[6] server.js conteudo:');
    try {
        const content = fs.readFileSync('/app/server.js', 'utf8');
        console.log(content.substring(0, 300));
    } catch(e) {
        console.log(`  Erro: ${e.message}`);
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('  FIM DO DIAGNOSTICO');
    console.log('='.repeat(60));
}

main().catch(console.error);
