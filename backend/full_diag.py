#!/usr/bin/env python3
"""
Script de diagnostico COMPLETO para rodar no container do BACKEND.
Copia tudo para o servidor e executa: python3 /app/full_diag.py
"""

import sys
import os
import json

print("=" * 70)
print("  DIAGNOSTICO COMPLETO - BACKEND + APPHEALTH")
print("=" * 70)

# 1. Backend responde?
print("\n[1] Backend local:")
try:
    import urllib.request
    r = urllib.request.urlopen("http://localhost:8000/")
    print(f"  OK: {r.read().decode()[:100]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 2. Todas as rotas
print("\n[2] Rotas registradas:")
try:
    from main import app
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path and not path.startswith("/openapi") and not path.startswith("/docs") and not path.startswith("/redoc"):
            print(f"  {sorted(methods)} {path}")
except Exception as e:
    print(f"  ERRO: {e}")

# 3. Preview endpoint
print("\n[3] GET /api/schedules/preview?date=2026-04-13:")
try:
    r = urllib.request.urlopen("http://localhost:8000/api/schedules/preview?date=2026-04-13")
    data = json.loads(r.read().decode())
    schedules = data.get("schedules", [])
    print(f"  STATUS: {r.status}")
    print(f"  TOTAL: {len(schedules)} agendamentos")
    if schedules:
        s = schedules[0]
        print(f"  EXEMPLO: {s.get('patient_name')} | {s.get('appointment_time')} | {s.get('patient_phone')}")
        # Verifica se todos tem telefone
        sem_tel = sum(1 for s in schedules if not s.get("patient_phone"))
        print(f"  SEM TELEFONE: {sem_tel}")
    else:
        print(f"  ATENCAO: Lista vazia!")
        print(f"  RAW RESPONSE: {json.dumps(data)[:300]}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read().decode()[:300]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 4. AppHealth direto - 13/04/2026
print("\n[4] AppHealth direto - 2026-04-13:")
try:
    import httpx
    import asyncio

    async def test_apphealth(date_str):
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            r = await client.get(
                "https://back.apphealth.com.br:9090/api-vizi/agendamentos",
                headers={"Authorization": "laVZIRHpJt1K9ygtRcDQfH7L1QmjHPN9qZ7l87Qp9PKLR"},
                params={"dataInicio": date_str, "dataFim": date_str},
            )
            return r.status_code, len(r.json()), r.json()[:1] if r.json() else []

    status, total, sample = asyncio.run(test_apphealth("2026-04-13"))
    print(f"  STATUS: {status}")
    print(f"  TOTAL: {total} agendamentos")
    if sample:
        s = sample[0]
        print(f"  CAMPOS: {list(s.keys())}")
        print(f"  EXEMPLO: nome={s.get('nome')} | tel={s.get('telefonePrincipal')} | hora={s.get('horaInicio')}")
except Exception as e:
    print(f"  ERRO: {e}")

# 5. Tentar acessar o backend EXTERNAMENTE (de dentro do container)
print("\n[5] Testando acesso externo ao backend (via hostname do servidor):")
hostname = os.environ.get("HOSTNAME_EXTERNAL", "")
if not hostname:
    # Tenta descobrir via DNS reverso ou variaveis
    print("  HOSTNAME_EXTERNAL nao definido, pulando...")
else:
    try:
        r = urllib.request.urlopen(f"{hostname}/api/schedules/preview?date=2026-04-13", timeout=5)
        print(f"  OK: {r.status} - {r.read().decode()[:200]}")
    except Exception as e:
        print(f"  ERRO: {e}")

# 6. Ver variaveis de ambiente
print("\n[6] Variaveis de ambiente relevantes:")
for key in sorted(os.environ.keys()):
    if any(k in key.lower() for k in ["api", "url", "host", "port", "public", "next", "backend"]):
        val = os.environ[key]
        masked = val[:20] + "..." if len(val) > 20 else val
        print(f"  {key}={masked}")

# 7. Testar DNS do AppHealth
print("\n[7] DNS do AppHealth:")
try:
    import socket
    ip = socket.gethostbyname("back.apphealth.com.br")
    print(f"  back.apphealth.com.br -> {ip}")
except Exception as e:
    print(f"  ERRO: {e}")

# 8. Conectividade outbound
print("\n[8] Conectividade outbound:")
for target in [("back.apphealth.com.br", 9090), ("agente-ia-agente-ia.rqn0xm.easypanel.host", 8000)]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        result = s.connect_ex(target)
        s.close()
        print(f"  {target[0]}:{target[1]} -> {'OK' if result == 0 else 'FALHOU (errno=' + str(result) + ')'}")
    except Exception as e:
        print(f"  {target[0]}:{target[1]} -> ERRO: {e}")

print("\n" + "=" * 70)
print("  FIM")
print("=" * 70)
