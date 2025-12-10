"""
Configurazione del gioco Lupus in Fabula con LLM.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum

from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()


class Role(Enum):
    """Ruoli disponibili nel gioco."""
    LUPO = "lupo"
    VEGGENTE = "veggente"
    CONTADINO = "contadino"


# Configurazione centralizzata dei ruoli (emoji e descrizioni)
ROLE_CONFIG = {
    Role.LUPO: {
        "emoji": "🐺",
        "description": "Sei un LUPO. Devi eliminare i contadini senza farti scoprire.",
    },
    Role.VEGGENTE: {
        "emoji": "🔮",
        "description": "Sei il VEGGENTE. Ogni notte scopri il ruolo di un giocatore. Guida il villaggio!",
    },
    Role.CONTADINO: {
        "emoji": "🌾",
        "description": "Sei un CONTADINO. Osserva e vota saggiamente per eliminare i lupi.",
    },
}


def get_role_emoji(role) -> str:
    """Restituisce l'emoji per un ruolo (accetta Role o stringa)."""
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return ""
    return ROLE_CONFIG.get(role, {}).get("emoji", "")


def get_role_description(role: Role) -> str:
    """Restituisce la descrizione del ruolo."""
    return ROLE_CONFIG.get(role, {}).get("description", "")


class GamePhase(Enum):
    """Fasi del gioco."""
    GIORNO_DISCUSSIONE = "giorno_discussione"
    GIORNO_VOTAZIONE = "giorno_votazione"
    NOTTE_DISCUSSIONE_LUPI = "notte_discussione_lupi"
    NOTTE_VOTAZIONE_LUPI = "notte_votazione_lupi"
    NOTTE_VEGGENTE = "notte_veggente"


@dataclass
class GameConfig:
    """Configurazione della partita."""
    num_players: int = 8
    
    # Distribuzione ruoli
    num_lupi: int = 2
    num_veggenti: int = 1
    # I restanti sono contadini (5)
    
    # Impostazioni discussione
    max_messages_per_discussion: int = 20  # Messaggi max per fase discussione
    max_messages_per_player_per_phase: int = 3  # Messaggi max per giocatore per fase
    talk_back: bool = True  # Se True, dà priorità ai giocatori menzionati nel messaggio precedente
    
    # Early stop per testing/debug (None = nessun limite)
    max_turns: int | None = 2  # Ferma la partita dopo N turni (giorno+notte = 1 turno)
    
    # Debug: salva tutti i prompt inviati agli LLM
    persist_prompts: bool = True
    
    # OpenRouter settings
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Temperature per le chiamate LLM
    llm_temperature: float = 0.8
    
    def validate(self):
        """Valida la configurazione."""
        total_special = self.num_lupi + self.num_veggenti
        if total_special > self.num_players:
            raise ValueError(f"Troppi ruoli speciali ({total_special}) per {self.num_players} giocatori")
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY non configurata")


# Modelli disponibili su OpenRouter per i giocatori
# Ogni modello ha un model_id (per OpenRouter) e uno short_name (nome del giocatore)
AVAILABLE_MODELS_2 = [
    {"model_id": "openai/gpt-4o", "short_name": "GPT-4o"},
    {"model_id": "openai/gpt-4o-mini", "short_name": "GPT-4o-mini"},
    {"model_id": "anthropic/claude-3.5-sonnet", "short_name": "Claude-3.5"},
    {"model_id": "anthropic/claude-3-haiku", "short_name": "Claude-Haiku"},
    {"model_id": "google/gemini-pro-1.5", "short_name": "Gemini-Pro"},
    {"model_id": "google/gemini-flash-1.5", "short_name": "Gemini-Flash"},
    {"model_id": "meta-llama/llama-3.1-70b-instruct", "short_name": "Llama-70B"},
    {"model_id": "meta-llama/llama-3.1-8b-instruct", "short_name": "Llama-8B"},
    {"model_id": "mistralai/mistral-large", "short_name": "Mistral-Large"},
    {"model_id": "mistralai/mixtral-8x7b-instruct", "short_name": "Mixtral-8x7B"},
]

# Modelli economici per testing (tutti openai/gpt-oss-20b)
# Colori ANSI per terminale
AVAILABLE_MODELS = [
    {"model_id": "openai/gpt-oss-20b", "short_name": "Marco", "color": "\033[91m"},    # Rosso
    {"model_id": "openai/gpt-oss-20b", "short_name": "Sofia", "color": "\033[92m"},    # Verde
    {"model_id": "openai/gpt-oss-20b", "short_name": "Luca", "color": "\033[93m"},     # Giallo
    {"model_id": "openai/gpt-oss-20b", "short_name": "Giulia", "color": "\033[94m"},   # Blu
    {"model_id": "deepseek/deepseek-v3.2", "short_name": "DeepSeek", "color": "\033[95m"},   # Magenta
    {"model_id": "openai/gpt-oss-20b", "short_name": "Elena", "color": "\033[96m"},    # Ciano
    {"model_id": "openai/gpt-oss-20b", "short_name": "Matteo", "color": "\033[97m"},   # Bianco
    {"model_id": "openai/gpt-oss-20b", "short_name": "Chiara", "color": "\033[38;5;208m"},  # Arancione (256 color)
]


def get_model_by_short_name(short_name: str) -> str:
    """Restituisce il model_id dato lo short_name."""
    for model in AVAILABLE_MODELS:
        if model["short_name"] == short_name:
            return model["model_id"]
    return AVAILABLE_MODELS[0]["model_id"]


def get_color_by_short_name(short_name: str) -> str:
    """Restituisce il codice colore ANSI dato lo short_name."""
    for model in AVAILABLE_MODELS:
        if model["short_name"] == short_name:
            return model.get("color", "\033[0m")
    return "\033[0m"  # Reset/default


def get_all_short_names() -> List[str]:
    """Restituisce tutti gli short_name disponibili."""
    return [m["short_name"] for m in AVAILABLE_MODELS]
