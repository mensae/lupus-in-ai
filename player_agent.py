"""
PlayerAgent: Wrapper attorno all'LLM con memoria locale (scratchpad).
"""
import httpx
import os
import re
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from config import Role, GameConfig


class ActionType(Enum):
    """Tipi di azione che un giocatore può compiere."""
    CHAT_PUBBLICO = "chat_pubblico"
    CHAT_LUPI = "chat_lupi"
    VOTO_GIORNO = "voto_giorno"
    VOTO_LUPI = "voto_lupi"
    VEGGENTE = "veggente"


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

GAME_RULES = """🐺 LUPUS IN FABULA - Gioco di deduzione sociale

REGOLE:
- I LUPI (nascosti) devono eliminare i contadini. Vincono se uguagliano o superano i non-lupi.
- Il VILLAGGIO deve scoprire e eliminare i lupi. Vince se elimina tutti i lupi.
- Il VEGGENTE può scoprire il ruolo di un giocatore ogni notte. È un alleato dei contadini.

FASI:
- NOTTE: I lupi scelgono chi uccidere. Il veggente investiga.
- ALBA: Si annuncia chi è morto (e il suo ruolo viene rivelato).
- GIORNO: Tutti discutono e votano per eliminare un sospetto.

Rispondi sempre in italiano."""


def _get_role_info(role: Role, wolf_teammates: List[str] = None) -> str:
    """Costruisce la descrizione del ruolo per il prompt."""
    from config import get_role_emoji, get_role_description
    emoji = get_role_emoji(role)
    desc = get_role_description(role)
    
    if role == Role.LUPO and wolf_teammates:
        return f"{emoji} {desc} Gli altri lupi sono: {', '.join(wolf_teammates)}"
    return f"{emoji} {desc}"


ACTION_PROMPTS = {
    ActionType.CHAT_PUBBLICO: """AZIONE: Scrivi un messaggio nella chat pubblica del villaggio.

Parla SOLO se porti avanti la conversazione in modo utile:
- Nuovi sospetti o informazioni
- Risposte a domande dirette
- Difesa se accusato

NON ripetere cose già dette. Se non hai nulla di nuovo da aggiungere, passa.
Nota: i messaggi [Sistema] non sono di un giocatore, sono annunci di gioco.

FORMATO RISPOSTA:
[PENSIERO] riflessione privata opzionale [/PENSIERO]
[MESSAGGIO] cosa dici agli altri (2-3 frasi max) [/MESSAGGIO]

Se non hai nulla di utile da dire: [MESSAGGIO][PASS][/MESSAGGIO]""",

    ActionType.CHAT_LUPI: """AZIONE: Scrivi un messaggio nella chat segreta dei lupi.

Discuti con gli altri lupi su chi uccidere stanotte.
Parla SOLO se hai qualcosa di utile da aggiungere. NON ripetere cose già dette.
Nota: i messaggi [Sistema] non sono di un giocatore, sono annunci di gioco.

FORMATO RISPOSTA:
[PENSIERO] riflessione privata opzionale [/PENSIERO]
[MESSAGGIO] cosa dici agli altri lupi (2-3 frasi max) [/MESSAGGIO]

Se non hai nulla di utile da dire: [MESSAGGIO][PASS][/MESSAGGIO]""",

    ActionType.VOTO_GIORNO: """AZIONE: Vota chi eliminare dal villaggio.

Candidati: {candidates}

FORMATO RISPOSTA:
Rispondi SOLO con il nome esatto di chi vuoi eliminare.
Puoi anche votare "nessuno".""",

    ActionType.VOTO_LUPI: """AZIONE: Vota chi uccidere stanotte.

Candidati: {candidates}

FORMATO RISPOSTA:
Rispondi SOLO con il nome esatto della vittima.""",

    ActionType.VEGGENTE: """AZIONE: Scegli chi investigare stanotte.

Candidati: {candidates}

FORMATO RISPOSTA:
[PENSIERO] perché vuoi investigare questa persona [/PENSIERO]
[MESSAGGIO] scrivi SOLO il nome della persona da investigare [/MESSAGGIO]""",
}


@dataclass
class PlayerAgent:
    """
    Rappresenta un giocatore controllato da un LLM.
    """
    name: str
    role: Role
    model: str
    config: GameConfig
    
    # Stato del giocatore
    is_alive: bool = True
    
    # Scratchpad: riflessioni personali (editate a fine giornata)
    scratchpad: List[str] = field(default_factory=list)
    
    # Ruoli scoperti dal veggente
    known_roles: Dict[str, Role] = field(default_factory=dict)
    
    # Compagni lupi
    wolf_teammates: List[str] = field(default_factory=list)
    
    # Lista di tutti i giocatori
    all_players: List[str] = field(default_factory=list)
    
    # Directory per salvare i prompt (set da game_engine)
    _prompts_dir: Optional[str] = field(default=None, repr=False)
    _prompt_counter: int = field(default=0, repr=False)
    
    def __post_init__(self):
        self._http_client = httpx.Client(timeout=60.0)
    
    def set_prompts_directory(self, prompts_dir: str):
        """Imposta la directory dove salvare i prompt."""
        self._prompts_dir = prompts_dir
    
    def _persist_prompt(self, prompt: str, response: str, action: str):
        """Salva prompt e risposta su file se PERSIST_PROMPTS è attivo."""
        if not self.config.persist_prompts or not self._prompts_dir:
            return
        
        self._prompt_counter += 1
        filepath = os.path.join(self._prompts_dir, f"{self.name}.txt")
        
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"PROMPT #{self._prompt_counter} - {action} - {datetime.now().isoformat()}\n")
            f.write(f"{'='*80}\n\n")
            f.write(prompt)
            f.write(f"\n\n{'-'*40}\n")
            f.write(f"RISPOSTA:\n{'-'*40}\n\n")
            f.write(response)
            f.write(f"\n\n")
    
    # =========================================================================
    # PROMPT BUILDING
    # =========================================================================
    
    def _build_prompt(
        self,
        action: ActionType,
        game_state: str,
        current_phase: str,
        chat_history: str = "",
        candidates: List[str] = None,
    ) -> str:
        """
        Costruisce il prompt completo per l'LLM.
        
        Struttura:
        1. Regole generali del gioco
        2. Il tuo ruolo
        3. Stato del gioco (giocatori, eventi pubblici, fase corrente)
        4. Il tuo scratchpad (riflessioni personali)
        5. [Se chat] Messaggi della chat corrente
        6. Azione richiesta
        """
        sections = []
        
        # 1. Regole generali
        sections.append(GAME_RULES)
        
        # 2. Il tuo ruolo
        role_text = _get_role_info(self.role, self.wolf_teammates)
        sections.append(f"---\nTU SEI: {self.name}\n{role_text}")
        
        # Aggiungi ruoli scoperti (per veggente)
        if self.known_roles:
            known = "\n".join([f"  - {p}: {r.value}" for p, r in self.known_roles.items()])
            sections.append(f"RUOLI SCOPERTI:\n{known}")
        
        # 3. Stato del gioco
        sections.append(f"---\n📋 STATO DEL GIOCO\n{game_state}")
        sections.append(f"⏰ FASE CORRENTE: {current_phase}")
        
        # 4. Scratchpad
        if self.scratchpad:
            scratchpad_text = "\n".join([f"  • {s}" for s in self.scratchpad])
            sections.append(f"---\n📝 LE TUE RIFLESSIONI:\n{scratchpad_text}")
        
        # 5. Chat history (solo per azioni chat)
        if chat_history and action in (ActionType.CHAT_PUBBLICO, ActionType.CHAT_LUPI):
            sections.append(f"---\n💬 CHAT CORRENTE:\n{chat_history}")
        
        # 6. Azione richiesta
        action_prompt = ACTION_PROMPTS[action]
        if candidates:
            action_prompt = action_prompt.format(candidates=", ".join(candidates))
        sections.append(f"---\n{action_prompt}")
        
        return "\n\n".join(sections)
    
    def _parse_response(self, response: str) -> Tuple[Optional[str], str]:
        """
        Parsa la risposta cercando i tag [PENSIERO] e [MESSAGGIO].
        
        Returns:
            (pensiero, messaggio): Tupla con pensiero opzionale e messaggio.
        """
        pensiero = None
        messaggio = response.strip()
        
        # Cerca [PENSIERO]
        pensiero_match = re.search(
            r'\[PENSIERO\](.*?)(?:\[/PENSIERO\]|\[MESSAGGIO\]|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if pensiero_match:
            pensiero = pensiero_match.group(1).strip()
        
        # Cerca [MESSAGGIO]
        messaggio_match = re.search(
            r'\[MESSAGGIO\](.*?)(?:\[/MESSAGGIO\]|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if messaggio_match:
            messaggio = messaggio_match.group(1).strip()
        else:
            # Fallback: rimuovi pensiero e usa il resto
            messaggio = re.sub(
                r'\[PENSIERO\].*?(?:\[/PENSIERO\]|$)', 
                '', 
                response, 
                flags=re.IGNORECASE | re.DOTALL
            ).strip()
        
        return pensiero, messaggio
    
    # =========================================================================
    # LLM CALL
    # =========================================================================
    
    def _call_llm(self, prompt: str, action: str = "unknown") -> str:
        """Chiama l'LLM via OpenRouter."""
        headers = {
            "Authorization": f"Bearer {self.config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lupus-in-ai.local",
            "X-Title": "Lupus in AI",
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.llm_temperature,
            "max_tokens": 500,
        }
        
        try:
            response = self._http_client.post(
                f"{self.config.openrouter_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()["choices"][0]["message"]["content"]
            
            # Salva prompt se persist_prompts è attivo
            self._persist_prompt(prompt, result, action)
            
            return result
        
        except Exception as e:
            print(f"[ERROR] LLM call failed for {self.name}: {e}")
            self._persist_prompt(prompt, f"[ERROR] {e}", action)
            return "[PASS]"
    
    # =========================================================================
    # AZIONI
    # =========================================================================
    
    def generate_chat_message(
        self,
        game_state: str,
        current_phase: str,
        chat_history: str,
        is_wolf_chat: bool = False,
    ) -> Tuple[Optional[str], str]:
        """
        Genera un messaggio per la chat (pubblica o lupi).
        
        Returns:
            (pensiero, messaggio): Pensiero opzionale e messaggio da inviare.
        """
        action = ActionType.CHAT_LUPI if is_wolf_chat else ActionType.CHAT_PUBBLICO
        
        prompt = self._build_prompt(
            action=action,
            game_state=game_state,
            current_phase=current_phase,
            chat_history=chat_history,
        )
        
        response = self._call_llm(prompt, action=action.value)
        return self._parse_response(response)
    
    def generate_vote(
        self,
        game_state: str,
        current_phase: str,
        candidates: List[str],
        is_wolf_vote: bool = False,
    ) -> str:
        """
        Genera un voto.
        
        Returns:
            Nome del giocatore votato o "nessuno".
        """
        action = ActionType.VOTO_LUPI if is_wolf_vote else ActionType.VOTO_GIORNO
        
        prompt = self._build_prompt(
            action=action,
            game_state=game_state,
            current_phase=current_phase,
            candidates=candidates,
        )
        
        response = self._call_llm(prompt, action=action.value).strip().strip('"').strip("'")
        
        # Cerca un nome valido
        for candidate in candidates:
            if candidate.lower() in response.lower():
                return candidate
        
        if "nessuno" in response.lower():
            return "nessuno"
        
        return candidates[0] if candidates else "nessuno"
    
    def generate_seer_choice(
        self,
        game_state: str,
        current_phase: str,
        candidates: List[str],
    ) -> Tuple[str, Optional[str]]:
        """
        Il veggente sceglie chi investigare.
        
        Returns:
            (target, reasoning): Nome e motivazione.
        """
        prompt = self._build_prompt(
            action=ActionType.VEGGENTE,
            game_state=game_state,
            current_phase=current_phase,
            candidates=candidates,
        )
        
        response = self._call_llm(prompt, action="veggente")
        reasoning, target = self._parse_response(response)
        target = target.strip().strip('"').strip("'")
        
        for candidate in candidates:
            if candidate.lower() in target.lower():
                return candidate, reasoning
        
        return (candidates[0] if candidates else ""), reasoning
    
    # =========================================================================
    # SCRATCHPAD
    # =========================================================================
    
    def update_scratchpad(self, thought: str):
        """Aggiunge un pensiero allo scratchpad."""
        self.scratchpad.append(thought)
    
    def edit_scratchpad(self, game_state: str) -> str:
        """
        Chiede all'LLM di rieditare lo scratchpad a fine giornata.
        Mantiene solo le informazioni chiave.
        """
        if not self.scratchpad:
            return ""
        
        current = "\n".join([f"• {s}" for s in self.scratchpad])
        
        prompt = f"""{GAME_RULES}

---
TU SEI: {self.name}

---
📋 STATO DEL GIOCO:
{game_state}

---
📝 LE TUE RIFLESSIONI ATTUALI:
{current}

---
AZIONE: Riscrivi le tue riflessioni in modo COMPATTO (max 5 punti).
Mantieni SOLO:
- Sospetti attuali e perché
- Fatti certi (chi è morto e che ruolo aveva)
- La tua strategia

Rispondi SOLO con i bullet points (uno per riga, inizia con "• ")."""

        response = self._call_llm(prompt, action="edit_scratchpad")
        
        # Estrai i bullet points
        lines = [l.strip() for l in response.split("\n") if l.strip()]
        new_scratchpad = []
        for line in lines:
            # Rimuovi eventuali marker
            clean = re.sub(r'^[•\-\*]\s*', '', line).strip()
            if clean:
                new_scratchpad.append(clean)
        
        self.scratchpad = new_scratchpad[:5]  # Max 5 punti
        return "\n".join([f"• {s}" for s in self.scratchpad])
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def kill(self):
        """Uccide il giocatore."""
        self.is_alive = False
    
    def __del__(self):
        """Cleanup."""
        if hasattr(self, '_http_client'):
            self._http_client.close()
