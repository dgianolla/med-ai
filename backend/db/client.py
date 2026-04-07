from supabase import create_client, Client
from config import get_settings

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """Retorna cliente Supabase com service_role key (bypass RLS — uso exclusivo backend)."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        # service_role bypassa RLS — nunca expor no frontend
        key = settings.supabase_service_role_key or settings.supabase_publishable_key
        _supabase_client = create_client(settings.supabase_url, key)
    return _supabase_client
