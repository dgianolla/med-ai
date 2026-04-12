#!/usr/bin/env python3
"""Script de diagnstico para rodar dentro do container do backend."""

import sys
import traceback

print("=" * 60)
print("  DIAGNSTICO DO BACKEND")
print("=" * 60)

# 1. Backend responde?
print("\n[1] Testando http://localhost:8000/")
try:
    import urllib.request
    r = urllib.request.urlopen("http://localhost:8000/")
    print(f"  STATUS: {r.status}")
    print(f"  BODY: {r.read().decode()[:200]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 2. Health check
print("\n[2] Testando http://localhost:8000/health")
try:
    r = urllib.request.urlopen("http://localhost:8000/health")
    print(f"  STATUS: {r.status}")
    print(f"  BODY: {r.read().decode()[:200]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 3. Rotas registradas
print("\n[3] Rotas registradas:")
try:
    from main import app
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path:
            marker = " <-- NOSSA" if "schedules" in path or "dashboard" in path or "leads" in path or "webhook" in path or "priority" in path else ""
            print(f"  {sorted(methods)} {path}{marker}")
except Exception as e:
    print(f"  ERRO: {e}")
    traceback.print_exc()

# 4. Endpoint preview
print("\n[4] Testando /api/schedules/preview?date=2026-04-13")
try:
    r = urllib.request.urlopen("http://localhost:8000/api/schedules/preview?date=2026-04-13")
    data = r.read().decode()
    print(f"  STATUS: {r.status}")
    print(f"  BODY: {data[:500]}")
except urllib.error.HTTPError as e:
    print(f"  HTTP ERROR: {e.code} - {e.read().decode()[:300]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 5. AppHealth direto
print("\n[5] Testando AppHealth direto:")
try:
    import httpx
    import asyncio

    async def test_apphealth():
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            r = await client.get(
                "https://back.apphealth.com.br:9090/api-vizi/agendamentos",
                headers={"Authorization": "laVZIRHpJt1K9ygtRcDQfH7L1QmjHPN9qZ7l87Qp9PKLR"},
                params={"dataInicio": "2026-04-13", "dataFim": "2026-04-13"},
            )
            return r.status_code, len(r.json())

    status, total = asyncio.run(test_apphealth())
    print(f"  STATUS: {status}")
    print(f"  TOTAL AGENDAMENTOS: {total}")
except ImportError:
    print(f"  httpx no instalado")
except Exception as e:
    print(f"  ERRO: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("  FIM DO DIAGNSTICO")
print("=" * 60)
