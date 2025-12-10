"""
TranscriptManager: Gestisce transcript, output a terminale e JSON progressivo.
"""
import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

# Codici ANSI per formattazione
RESET = "\033[0m"
ITALIC = "\033[3m"
BOLD = "\033[1m"


class MessageType(Enum):
    """Tipi di messaggio nel transcript."""
    CHAT_PUBBLICO = "chat_pubblico"
    CHAT_LUPI = "chat_lupi"
    PENSIERO = "pensiero"
    SISTEMA = "sistema"
    VOTO = "voto"


class TranscriptManager:
    """
    Gestisce il transcript del gioco:
    - Scrive eventi a terminale in tempo reale
    - Mantiene JSON organizzato per fasi
    - Salva su file strada facendo (ogni fase)
    """
    
    def __init__(self, game_id: Optional[str] = None):
        self._game_id = game_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._game_dir: Optional[str] = None
        self._json_path: Optional[str] = None
        
        # Struttura JSON principale
        self._game_data: Dict[str, Any] = {
            "game_id": self._game_id,
            "start_time": datetime.now().isoformat(),
            "players": {},
            "phases": [],
            "winner": None,
            "end_time": None,
        }
        
        # Fase corrente
        self._current_phase: Optional[Dict[str, Any]] = None
        self._current_phase_name: str = ""
        self._current_turn: int = 0
        
        # Inner dialogues (per report finale)
        self._inner_dialogues: Dict[str, List[Dict]] = {}
        
        # Ruoli giocatori (per emoji display)
        self._player_roles: Dict[str, str] = {}
    
    # =========================================================================
    # SETUP
    # =========================================================================
    
    def setup_game_directory(self, base_dir: str = "transcripts") -> str:
        """Crea la directory e inizializza il JSON."""
        self._game_dir = os.path.join(base_dir, f"game_{self._game_id}")
        os.makedirs(self._game_dir, exist_ok=True)
        
        self._json_path = os.path.join(self._game_dir, "game_log.json")
        self._save_json()
        
        return self._game_dir
    
    def get_game_directory(self) -> Optional[str]:
        return self._game_dir
    
    def set_players_info(self, players_info: Dict[str, dict]):
        """Imposta info giocatori e salva."""
        self._game_data["players"] = players_info
        # Salva ruoli per emoji display
        self._player_roles = {name: info.get("role", "") for name, info in players_info.items()}
        self._save_json()
    
    # =========================================================================
    # GESTIONE FASI
    # =========================================================================
    
    def start_phase(self, turn: int, phase_name: str):
        """
        Inizia una nuova fase del gioco.
        Chiude la fase precedente se esiste.
        """
        # Chiudi fase precedente
        if self._current_phase is not None:
            self._end_current_phase()
        
        self._current_turn = turn
        self._current_phase_name = phase_name
        
        # Nuova fase
        self._current_phase = {
            "turn": turn,
            "phase": phase_name,
            "start_time": datetime.now().isoformat(),
            "events": [],
            "end_time": None,
        }
        
        # Header a terminale
        print(f"\n{'='*50}")
        print(f"📍 {phase_name}")
        print(f"{'='*50}")
    
    def _end_current_phase(self):
        """Chiude la fase corrente e salva."""
        if self._current_phase:
            self._current_phase["end_time"] = datetime.now().isoformat()
            self._game_data["phases"].append(self._current_phase)
            self._save_json()
            self._current_phase = None
    
    def set_turn_and_phase(self, turn: int, phase_name: str):
        """Alias per start_phase (retrocompatibilità)."""
        self.start_phase(turn, phase_name)
    
    # =========================================================================
    # AGGIUNTA EVENTI
    # =========================================================================
    
    def _get_player_color(self, player_name: str) -> str:
        """Ottiene il colore ANSI per un giocatore."""
        from config import get_color_by_short_name
        return get_color_by_short_name(player_name)
    
    def _get_role_emoji(self, player_name: str) -> str:
        """Ottiene l'emoji del ruolo per un giocatore (solo per display)."""
        if player_name in self._player_roles:
            from config import get_role_emoji
            return get_role_emoji(self._player_roles[player_name])
        return ""
    
    def add_system_message(self, content: str):
        """Aggiunge messaggio di sistema."""
        self._add_event(MessageType.SISTEMA, "Sistema", content)
        print(f"📢 {content}")
    
    def add_public_message(self, sender: str, content: str):
        """Aggiunge messaggio chat pubblica."""
        self._add_event(MessageType.CHAT_PUBBLICO, sender, content)
        color = self._get_player_color(sender)
        role_emoji = self._get_role_emoji(sender)
        print(f"💬 {color}[{role_emoji} {sender}]{RESET}: {content}")
    
    def add_wolf_message(self, sender: str, content: str):
        """Aggiunge messaggio chat lupi."""
        self._add_event(MessageType.CHAT_LUPI, sender, content)
        color = self._get_player_color(sender)
        role_emoji = self._get_role_emoji(sender)
        print(f"💬 {color}[{role_emoji} {sender}]{RESET}: {content}")
    
    def add_vote(self, voter: str, target: str, is_wolf_vote: bool = False):
        """Aggiunge un voto."""
        msg_type = MessageType.CHAT_LUPI if is_wolf_vote else MessageType.VOTO
        content = f"vota {target}"
        self._add_event(msg_type, voter, content, extra={"target": target})
        
        color = self._get_player_color(voter)
        role_emoji = self._get_role_emoji(voter)
        print(f"🗳️ {color}{role_emoji} {voter}{RESET} vota: {target}")
    
    def add_inner_dialogue(self, player_name: str, content: str):
        """Aggiunge pensiero privato."""
        # Salva nell'evento corrente
        self._add_event(MessageType.PENSIERO, player_name, content)
        
        # Stampa a terminale (pensiero in italics)
        color = self._get_player_color(player_name)
        role_emoji = self._get_role_emoji(player_name)
        print(f"💭 {color}[{role_emoji} {player_name}]{RESET}: {ITALIC}{content}{RESET}")
        
        # Salva anche in struttura separata per report
        if player_name not in self._inner_dialogues:
            self._inner_dialogues[player_name] = []
        
        self._inner_dialogues[player_name].append({
            "turn": self._current_turn,
            "phase": self._current_phase_name,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
    
    def _add_event(self, msg_type: MessageType, sender: str, content: str, extra: Optional[dict] = None):
        """Aggiunge evento alla fase corrente."""
        if self._current_phase is None:
            return
        
        event = {
            "type": msg_type.value,
            "sender": sender,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if extra:
            event.update(extra)
        
        self._current_phase["events"].append(event)
    
    # =========================================================================
    # FORMATTAZIONE PER PROMPT (compatibilità con game_engine)
    # =========================================================================
    
    def format_public_history_for_prompt(self, max_messages: Optional[int] = None) -> str:
        """Formatta chat pubblica per i prompt (solo turno corrente)."""
        messages = []
        
        # Prendi solo messaggi del turno corrente dalle fasi salvate
        for phase in self._game_data["phases"]:
            if phase["turn"] == self._current_turn:
                for event in phase["events"]:
                    if event["type"] in ("chat_pubblico", "sistema", "voto"):
                        if event["type"] == "voto":
                            messages.append(f"[{event['sender']}]: vota {event.get('target', '?')}")
                        else:
                            messages.append(f"[{event['sender']}]: {event['content']}")
        
        # Aggiungi anche fase corrente (se stesso turno)
        if self._current_phase and self._current_phase.get("turn") == self._current_turn:
            for event in self._current_phase["events"]:
                if event["type"] in ("chat_pubblico", "sistema", "voto"):
                    if event["type"] == "voto":
                        messages.append(f"[{event['sender']}]: vota {event.get('target', '?')}")
                    else:
                        messages.append(f"[{event['sender']}]: {event['content']}")
        
        if max_messages:
            messages = messages[-max_messages:]
        
        return "\n".join(messages) if messages else "Nessuna discussione precedente."
    
    def format_wolf_history_for_prompt(self, max_messages: Optional[int] = None) -> str:
        """Formatta chat lupi per i prompt (solo notte corrente)."""
        messages = []
        
        # Prendi solo messaggi del turno corrente
        for phase in self._game_data["phases"]:
            if phase["turn"] == self._current_turn:
                for event in phase["events"]:
                    if event["type"] == "chat_lupi":
                        messages.append(f"[{event['sender']}]: {event['content']}")
        
        if self._current_phase and self._current_phase.get("turn") == self._current_turn:
            for event in self._current_phase["events"]:
                if event["type"] == "chat_lupi":
                    messages.append(f"[{event['sender']}]: {event['content']}")
        
        if max_messages:
            messages = messages[-max_messages:]
        
        return "\n".join(messages) if messages else "Nessuna discussione precedente tra i lupi."
    
    # =========================================================================
    # SALVATAGGIO E REPORT
    # =========================================================================
    
    def _save_json(self):
        """Salva il JSON su file."""
        if not self._json_path:
            return
        
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(self._game_data, f, ensure_ascii=False, indent=2)
    
    def finalize_game(self, winner: str):
        """Chiude la partita e genera report finale."""
        # Chiudi ultima fase
        self._end_current_phase()
        
        # Aggiorna dati finali
        self._game_data["winner"] = winner
        self._game_data["end_time"] = datetime.now().isoformat()
        self._game_data["inner_dialogues"] = self._inner_dialogues
        
        # Calcola statistiche
        stats = self._calculate_stats()
        self._game_data["statistics"] = stats
        
        # Salva JSON finale
        self._save_json()
        
        # Genera report markdown
        self._generate_markdown_report(winner)
        
        return self._json_path
    
    def _calculate_stats(self) -> dict:
        """Calcola statistiche della partita."""
        total_events = 0
        chat_pubblico = 0
        chat_lupi = 0
        voti = 0
        pensieri = 0
        sistema = 0
        
        for phase in self._game_data["phases"]:
            for event in phase["events"]:
                total_events += 1
                t = event["type"]
                if t == "chat_pubblico":
                    chat_pubblico += 1
                elif t == "chat_lupi":
                    chat_lupi += 1
                elif t == "voto":
                    voti += 1
                elif t == "pensiero":
                    pensieri += 1
                elif t == "sistema":
                    sistema += 1
        
        return {
            "total_events": total_events,
            "chat_pubblico": chat_pubblico,
            "chat_lupi": chat_lupi,
            "voti": voti,
            "pensieri": pensieri,
            "sistema": sistema,
            "num_phases": len(self._game_data["phases"]),
        }
    
    def _generate_markdown_report(self, winner: str):
        """Genera report markdown."""
        if not self._game_dir:
            return
        
        report_path = os.path.join(self._game_dir, "REPORT.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            # Header
            f.write("# 🐺 LUPUS IN AI - Report Partita\n\n")
            f.write(f"**ID:** {self._game_id}\n")
            f.write(f"**Inizio:** {self._game_data['start_time']}\n")
            f.write(f"**Fine:** {self._game_data['end_time']}\n")
            f.write(f"**Vincitore:** {'🐺 LUPI' if winner == 'lupi' else '🌾 VILLAGGIO'}\n\n")
            
            # Giocatori
            f.write("## 👥 Giocatori\n\n")
            f.write("| Nome | Ruolo | Modello | Vivo |\n")
            f.write("|------|-------|---------|------|\n")
            
            from config import get_role_emoji
            for name, info in self._game_data["players"].items():
                emoji = get_role_emoji(info.get("role", ""))
                alive = "✅" if info.get("alive", False) else "❌"
                f.write(f"| {name} | {emoji} {info.get('role', '?')} | {info.get('model', '?')} | {alive} |\n")
            
            f.write("\n")
            
            # Cronologia
            f.write("## 📜 Cronologia\n\n")
            
            for phase in self._game_data["phases"]:
                f.write(f"### {phase['phase']}\n\n")
                
                for event in phase["events"]:
                    t = event["type"]
                    sender = event["sender"]
                    content = event["content"]
                    
                    if t == "sistema":
                        f.write(f"**📢 {content}**\n\n")
                    elif t == "chat_pubblico":
                        f.write(f"**[{sender}]:** {content}\n\n")
                    elif t == "chat_lupi":
                        f.write(f"🐺 **[{sender}]:** {content}\n\n")
                    elif t == "voto":
                        f.write(f"🗳️ {sender} vota {event.get('target', '?')}\n\n")
                    # Pensieri non inclusi nel report principale
            
            # Pensieri (sezione separata)
            f.write("## 🧠 Pensieri dei Giocatori\n\n")
            
            for player_name, thoughts in self._inner_dialogues.items():
                role = self._game_data["players"].get(player_name, {}).get("role", "?")
                emoji = get_role_emoji(role)
                f.write(f"### {player_name} ({emoji} {role})\n\n")
                
                for thought in thoughts:
                    f.write(f"**[Turno {thought['turn']} - {thought['phase']}]**\n")
                    f.write(f"> {thought['content']}\n\n")
            
            # Statistiche
            stats = self._game_data.get("statistics", {})
            f.write("## 📊 Statistiche\n\n")
            f.write(f"- Fasi totali: {stats.get('num_phases', 0)}\n")
            f.write(f"- Eventi totali: {stats.get('total_events', 0)}\n")
            f.write(f"- Chat pubblica: {stats.get('chat_pubblico', 0)}\n")
            f.write(f"- Chat lupi: {stats.get('chat_lupi', 0)}\n")
            f.write(f"- Voti: {stats.get('voti', 0)}\n")
    
    def get_statistics(self) -> dict:
        """Restituisce statistiche correnti."""
        return self._calculate_stats()
    
    # =========================================================================
    # RETROCOMPATIBILITÀ
    # =========================================================================
    
    def generate_final_report(self, winner: str) -> str:
        """Wrapper per finalize_game (retrocompatibilità)."""
        self.finalize_game(winner)
        if self._game_dir:
            return os.path.join(self._game_dir, "REPORT.md")
        return ""
