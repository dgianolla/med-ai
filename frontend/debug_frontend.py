#!/usr/bin/env python3
"""Script de diagnstico para rodar dentro do container do FRONTEND."""

import sys
import os
import json

print("=" * 60)
print("  DIAGNSTICO DO FRONTEND")
print("=" * 60)

# 1. Variavel NEXT_PUBLIC_API_URL (build-time em Next.js)
print("\n[1] NEXT_PUBLIC_API_URL:")
env_val = os.environ.get("NEXT_PUBLIC_API_URL", "NAO DEFINIDO")
print(f"  ENV: {env_val}")

# 2. Buscar no bundle compilado o valor real
print("\n[2] Buscando API_URL no bundle compilado:")
import subprocess
try:
    # Next.js standalone - procura no .next/standalone
    result = subprocess.run(
        ["grep", "-r", "NEXT_PUBLIC_API_URL", "/app/.next/standalone/", "/app/.next/static/"],
        capture_output=True, text=True, timeout=5
    )
    # Filtra so a primeira ocorrencia relevante
    for line in result.stdout.split("\n")[:5]:
        if line.strip():
            print(f"  {line[:200]}")
except Exception as e:
    print(f"  Nao encontrou em .next: {e}")

# 3. Testar acesso ao backend a partir do container frontend
print("\n[3] Testando conexao com o backend:")
backend_url = env_val if env_val != "NAO DEFINIDO" else "http://127.0.0.1:8000"
print(f"  URL sendo usada: {backend_url}")
try:
    import urllib.request
    r = urllib.request.urlopen(f"{backend_url}/api/schedules/preview?date=2026-04-13", timeout=5)
    data = json.loads(r.read().decode())
    print(f"  STATUS: {r.status}")
    print(f"  SCHEDULES: {len(data.get('schedules', []))}")
except urllib.error.HTTPError as e:
    print(f"  HTTP ERROR: {e.code} - {e.read().decode()[:200]}")
except Exception as e:
    print(f"  ERRO: {e}")

# 4. Arquivos estticos do Next.js
print("\n[4] Estrutura do app:")
for path in ["/app/.next/standalone", "/app/.next/static", "/app/package.json"]:
    exists = os.path.exists(path)
    print(f"  {path}: {'OK' if exists else 'NAO EXISTE'}")

# 5. Portas ouvindo
print("\n[5] Portas ouvindo (netstat):")
try:
    result = subprocess.run(
        ["netstat", "-tlnp"],
        capture_output=True, text=True, timeout=5
    )
    for line in result.stdout.split("\n"):
        if "LISTEN" in line:
            print(f"  {line.strip()}")
except FileNotFoundError:
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            if "LISTEN" in line:
                print(f"  {line.strip()}")
    except Exception:
        print("  netstat/ss nao disponiveis")

print("\n" + "=" * 60)
print("  FIM DO DIAGNSTICO DO FRONTEND")
print("=" * 60)
