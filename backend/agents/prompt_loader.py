from pathlib import Path
from functools import lru_cache

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@lru_cache(maxsize=10)
def load_prompt(name: str) -> str:
    """Carrega prompt do arquivo .md. Cached em memória após primeiro load."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")
