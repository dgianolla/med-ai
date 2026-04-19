from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str

    # Groq
    groq_api_key: str = ""

    # Supabase
    supabase_url: str
    supabase_publishable_key: str
    supabase_service_role_key: str = ""
    database_url: str

    # Upstash Redis
    upstash_redis_url: str = ""
    upstash_redis_token: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # wts.chat
    wts_api_url: str = "https://api.wts.chat"
    wts_api_key: str = ""
    wts_confirmation_channel_id: str = ""
    wts_confirmation_from_phone: str = ""

    # wts.chat chatbot trigger
    wts_chatbot_send_url: str = "https://api.helena.run/chat/v1/chatbot/send"
    wts_confirmation_chatbot_id: str = ""
    wts_confirmation_trigger_delay_seconds: int = 3

    # App
    port: int = 8000
    environment: str = "development"
    session_ttl_seconds: int = 1800
    message_buffer_seconds: int = 10
    message_buffer_ttl_seconds: int = 120
    webhook_secret: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
