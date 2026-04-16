import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.webhook import router as webhook_router
from routes.confirmation_webhook import router as confirmation_webhook_router
from routes.dashboard import router as dashboard_router
from routes.schedules import router as schedules_router
from routes.leads import router as leads_router
from routes.priority_leads import router as priority_leads_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="med-ai",
    description="Orquestração de agentes para clínica médica",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir em produção para o domínio do painel
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(confirmation_webhook_router)
app.include_router(dashboard_router)
app.include_router(schedules_router)
app.include_router(leads_router)
app.include_router(priority_leads_router)


@app.get("/")
async def root():
    return {"service": "med-ai", "status": "running"}
