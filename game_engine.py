"""
GameEngine: Gestisce lo stato del gioco, i ruoli e il flusso notte-giorno.
"""
import os
import random
import re
from typing import List, Dict, Optional, Tuple
from collections import Counter

from config import Role, GamePhase, GameConfig, AVAILABLE_MODELS, get_role_emoji
from player_agent import PlayerAgent
from transcript_manager import TranscriptManager


class GameEngine:
    """
    Motore principale del gioco Lupus in Fabula.
    """
    
    def __init__(self, config: Optional[GameConfig] = None, game_id: Optional[str] = None):
        self.config = config or GameConfig()
        self.config.validate()
        
        # Stato del gioco
        self.players: Dict[str, PlayerAgent] = {}
        self.transcript = TranscriptManager(game_id=game_id)
        
        # Turno e fase correnti
        self.current_turn: int = 0
        self.current_phase: GamePhase = GamePhase.GIORNO_DISCUSSIONE
        
        # Stato notte
        self.wolf_target: Optional[str] = None
        
        # Giocatori morti (con ruolo rivelato)
        self.dead_players: Dict[str, Role] = {}
        
        # Eventi pubblici (log di tutto ciò che è successo)
        self.public_events: List[str] = []
        
        # Flag fine gioco
        self.game_over: bool = False
        self.winner: Optional[str] = None
    
    # =========================================================================
    # SETUP
    # =========================================================================
    
    def setup_game(self, model_assignments: Optional[Dict[str, str]] = None):
        """Prepara una nuova partita."""
        print("\n🎮 Preparazione partita Lupus in Fabula...")
        
        # 1. Genera ruoli
        roles = self._generate_roles()
        random.shuffle(roles)
        
        # 2. Seleziona modelli
        if model_assignments is None:
            selected_models = random.sample(
                AVAILABLE_MODELS, 
                min(self.config.num_players, len(AVAILABLE_MODELS))
            )
            while len(selected_models) < self.config.num_players:
                selected_models.append(random.choice(AVAILABLE_MODELS))
        else:
            selected_models = list(model_assignments.values())
        
        player_names = [m["short_name"] for m in selected_models]
        
        # 3. Crea giocatori
        for i, model_info in enumerate(selected_models):
            name = model_info["short_name"]
            player = PlayerAgent(
                name=name,
                role=roles[i],
                model=model_info["model_id"],
                config=self.config,
                all_players=player_names,
            )
            self.players[name] = player
        
        # 4. Configura lupi
        wolf_names = [n for n, p in self.players.items() if p.role == Role.LUPO]
        for name in wolf_names:
            self.players[name].wolf_teammates = [n for n in wolf_names if n != name]
        
        # 5. Setup transcript
        self.transcript.setup_game_directory()
        self._update_transcript_players_info()
        
        # 6. Setup directory prompts (se persist_prompts è attivo)
        if self.config.persist_prompts:
            prompts_dir = os.path.join(self.transcript.get_game_directory(), "prompts")
            os.makedirs(prompts_dir, exist_ok=True)
            for player in self.players.values():
                player.set_prompts_directory(prompts_dir)
        
        # 7. Log
        self._log_setup()
        
        print("✅ Partita pronta!")
        print(f"   Giocatori: {len(self.players)}")
        print(f"   Lupi: {len(wolf_names)}")
        print(f"   📁 Directory: {self.transcript.get_game_directory()}")
        
        return self
    
    def _generate_roles(self) -> List[Role]:
        roles = []
        roles.extend([Role.LUPO] * self.config.num_lupi)
        roles.extend([Role.VEGGENTE] * self.config.num_veggenti)
        num_contadini = self.config.num_players - len(roles)
        roles.extend([Role.CONTADINO] * num_contadini)
        return roles
    
    def _log_setup(self):
        print("\n📋 Assegnazione ruoli (DEBUG):")
        for name, player in self.players.items():
            print(f"   {name}: {player.role.value}")
    
    def _update_transcript_players_info(self):
        self.transcript.set_players_info({
            name: {
                "role": p.role.value,
                "model": p.model,
                "alive": p.is_alive,
            }
            for name, p in self.players.items()
        })
    
    # =========================================================================
    # GAME STATE (per i prompt)
    # =========================================================================
    
    def get_game_state(self) -> str:
        """
        Genera lo stato del gioco per i prompt.
        Include: giocatori (vivi/morti con ruoli rivelati) e eventi pubblici.
        """
        lines = []
        
        # Giocatori vivi
        alive = self.get_alive_players()
        lines.append(f"GIOCATORI VIVI ({len(alive)}): {', '.join(alive)}")
        
        # Giocatori morti (con ruoli rivelati)
        if self.dead_players:
            dead_info = []
            for name, role in self.dead_players.items():
                emoji = get_role_emoji(role)
                dead_info.append(f"{name} ({emoji}{role.value})")
            lines.append(f"ELIMINATI: {', '.join(dead_info)}")
        
        # Eventi pubblici
        if self.public_events:
            lines.append("\nEVENTI:")
            for event in self.public_events:
                lines.append(f"  • {event}")
        
        return "\n".join(lines)
    
    def get_current_phase_name(self) -> str:
        """Restituisce il nome della fase corrente."""
        phase_names = {
            GamePhase.GIORNO_DISCUSSIONE: f"Giorno {self.current_turn} - Discussione",
            GamePhase.GIORNO_VOTAZIONE: f"Giorno {self.current_turn} - Votazione",
            GamePhase.NOTTE_DISCUSSIONE_LUPI: f"Notte {self.current_turn} - Lupi",
            GamePhase.NOTTE_VOTAZIONE_LUPI: f"Notte {self.current_turn} - Voto Lupi",
            GamePhase.NOTTE_VEGGENTE: f"Notte {self.current_turn} - Veggente",
        }
        return phase_names.get(self.current_phase, str(self.current_phase))
    
    def add_public_event(self, event: str):
        """Aggiunge un evento pubblico."""
        self.public_events.append(event)
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def get_alive_players(self) -> List[str]:
        return [n for n, p in self.players.items() if p.is_alive]
    
    def get_alive_wolves(self) -> List[str]:
        return [n for n, p in self.players.items() if p.is_alive and p.role == Role.LUPO]
    
    def get_alive_villagers(self) -> List[str]:
        return [n for n, p in self.players.items() if p.is_alive and p.role != Role.LUPO]
    
    def _kill_player(self, name: str) -> Role:
        player = self.players[name]
        role = player.role
        player.kill()
        self.dead_players[name] = role
        return role
    
    def _is_pass_message(self, message: str) -> bool:
        if not message or not message.strip():
            return True
        return "[PASS]" in message.upper() or message.strip().upper() == "PASS"
    
    def _find_mentioned_players(self, message: str, eligible: List[str]) -> List[str]:
        mentioned = []
        msg_lower = message.lower()
        for player in eligible:
            if re.search(r'\b' + re.escape(player.lower()) + r'\b', msg_lower):
                mentioned.append(player)
        return mentioned
    
    # =========================================================================
    # CONTROLLO VITTORIA
    # =========================================================================
    
    def check_game_over(self) -> Tuple[bool, Optional[str]]:
        wolves = len(self.get_alive_wolves())
        villagers = len(self.get_alive_villagers())
        
        if wolves >= villagers:
            self.game_over = True
            self.winner = "lupi"
            return True, "lupi"
        
        if wolves == 0:
            self.game_over = True
            self.winner = "villaggio"
            return True, "villaggio"
        
        return False, None
    
    # =========================================================================
    # FASI DI GIOCO
    # =========================================================================
    
    def run_day_discussion(self):
        """Fase discussione diurna."""
        self.current_phase = GamePhase.GIORNO_DISCUSSIONE
        phase_name = self.get_current_phase_name()
        self.transcript.set_turn_and_phase(self.current_turn, phase_name)
        
        alive = self.get_alive_players()
        game_state = self.get_game_state()
        msg_count = 0
        player_msg_count: Dict[str, int] = {p: 0 for p in alive}
        last_message = ""
        last_speaker = ""
        consecutive_passes = 0  # Conta pass consecutivi
        
        while msg_count < self.config.max_messages_per_discussion:
            eligible = [p for p in alive 
                       if player_msg_count[p] < self.config.max_messages_per_player_per_phase
                       and p != last_speaker]  # Escludi ultimo speaker
            if not eligible:
                break
            
            # Se tutti hanno passato di fila, termina discussione
            if consecutive_passes >= len(alive):
                self.transcript.add_system_message("La discussione si conclude.")
                break
            
            # Talk-back: priorità a chi è stato menzionato
            speaker_name = None
            if self.config.talk_back and last_message and last_speaker:
                candidates = [p for p in eligible if p != last_speaker]
                mentioned = self._find_mentioned_players(last_message, candidates)
                if mentioned:
                    speaker_name = mentioned[0]
            
            if speaker_name is None:
                speaker_name = random.choice(eligible)
            
            speaker = self.players[speaker_name]
            chat_history = self.transcript.format_public_history_for_prompt()
            
            # Genera messaggio
            pensiero, messaggio = speaker.generate_chat_message(
                game_state=game_state,
                current_phase=phase_name,
                chat_history=chat_history,
                is_wolf_chat=False,
            )
            
            # Salva pensiero nello scratchpad
            if pensiero:
                speaker.update_scratchpad(pensiero)
                self.transcript.add_inner_dialogue(speaker_name, pensiero)
            
            # Pubblica messaggio (se non PASS)
            if not self._is_pass_message(messaggio):
                self.transcript.add_public_message(speaker_name, messaggio)
                last_message = messaggio
                last_speaker = speaker_name
                consecutive_passes = 0  # Reset contatore
            else:
                last_message = ""
                last_speaker = ""
                consecutive_passes += 1  # Incrementa contatore pass
            
            player_msg_count[speaker_name] += 1
            msg_count += 1
    
    def run_day_voting(self) -> Optional[str]:
        """Fase votazione diurna."""
        self.current_phase = GamePhase.GIORNO_VOTAZIONE
        phase_name = self.get_current_phase_name()
        self.transcript.set_turn_and_phase(self.current_turn, phase_name)
        
        alive = self.get_alive_players()
        game_state = self.get_game_state()
        votes: Dict[str, str] = {}
        
        for voter_name in alive:
            voter = self.players[voter_name]
            candidates = [p for p in alive if p != voter_name]
            
            vote = voter.generate_vote(
                game_state=game_state,
                current_phase=phase_name,
                candidates=candidates,
                is_wolf_vote=False,
            )
            votes[voter_name] = vote
            self.transcript.add_vote(voter_name, vote, is_wolf_vote=False)
        
        # Conta voti
        vote_counts = Counter(votes.values())
        vote_counts.pop("nessuno", None)
        
        # Mostra conteggio voti
        if vote_counts:
            conteggio = ", ".join([f"{name}: {count}" for name, count in vote_counts.most_common()])
            self.transcript.add_system_message(f"📊 Conteggio: {conteggio}")
        
        if not vote_counts:
            self.transcript.add_system_message("Nessuno viene eliminato.")
            return None
        
        max_votes = max(vote_counts.values())
        most_voted = [n for n, c in vote_counts.items() if c == max_votes]
        threshold = len(alive) // 2 + 1
        
        if max_votes >= threshold and len(most_voted) == 1:
            eliminated = most_voted[0]
            role = self._kill_player(eliminated)
            
            event = f"Giorno {self.current_turn}: {eliminated} eliminato dal villaggio (era {role.value})"
            self.add_public_event(event)
            
            self.transcript.add_system_message(f"⚰️ {eliminated} eliminato! Era un {role.value}.")
            return eliminated
        else:
            self.transcript.add_system_message("Nessuna maggioranza. Nessuno eliminato.")
            return None
    
    def run_night_wolf_discussion(self):
        """Discussione notturna lupi."""
        self.current_phase = GamePhase.NOTTE_DISCUSSIONE_LUPI
        phase_name = self.get_current_phase_name()
        self.transcript.set_turn_and_phase(self.current_turn, phase_name)
        
        wolves = self.get_alive_wolves()
        if not wolves:
            return
        
        game_state = self.get_game_state()
        msg_count = 0
        wolf_msg_count: Dict[str, int] = {w: 0 for w in wolves}
        
        last_speaker = ""
        consecutive_passes = 0  # Conta pass consecutivi
        while msg_count < self.config.max_messages_per_discussion // 2:
            eligible = [w for w in wolves 
                       if wolf_msg_count[w] < self.config.max_messages_per_player_per_phase
                       and w != last_speaker]  # Escludi ultimo speaker
            if not eligible:
                break
            
            # Se tutti hanno passato di fila, termina discussione
            if consecutive_passes >= len(wolves):
                break
            
            speaker_name = random.choice(eligible)
            speaker = self.players[speaker_name]
            chat_history = self.transcript.format_wolf_history_for_prompt()
            
            pensiero, messaggio = speaker.generate_chat_message(
                game_state=game_state,
                current_phase=phase_name,
                chat_history=chat_history,
                is_wolf_chat=True,
            )
            
            if pensiero:
                speaker.update_scratchpad(pensiero)
                self.transcript.add_inner_dialogue(speaker_name, pensiero)
            
            if not self._is_pass_message(messaggio):
                self.transcript.add_wolf_message(speaker_name, messaggio)
                last_speaker = speaker_name
                consecutive_passes = 0
            else:
                last_speaker = ""
                consecutive_passes += 1
            
            wolf_msg_count[speaker_name] += 1
            msg_count += 1
    
    def run_night_wolf_voting(self) -> Optional[str]:
        """Voto lupi per la vittima."""
        self.current_phase = GamePhase.NOTTE_VOTAZIONE_LUPI
        phase_name = self.get_current_phase_name()
        self.transcript.set_turn_and_phase(self.current_turn, phase_name)
        
        wolves = self.get_alive_wolves()
        if not wolves:
            return None
        
        villagers = self.get_alive_villagers()
        game_state = self.get_game_state()
        votes: Dict[str, str] = {}
        
        for wolf_name in wolves:
            wolf = self.players[wolf_name]
            vote = wolf.generate_vote(
                game_state=game_state,
                current_phase=phase_name,
                candidates=villagers,
                is_wolf_vote=True,
            )
            votes[wolf_name] = vote
            self.transcript.add_vote(wolf_name, vote, is_wolf_vote=True)
        
        vote_counts = Counter(votes.values())
        most_voted = vote_counts.most_common(1)
        
        if most_voted:
            self.wolf_target = most_voted[0][0]
            self.transcript.add_system_message(f"🎯 Target lupi: {self.wolf_target}")
            return self.wolf_target
        
        return None
    
    def run_night_seer(self):
        """Il veggente investiga."""
        self.current_phase = GamePhase.NOTTE_VEGGENTE
        phase_name = self.get_current_phase_name()
        self.transcript.set_turn_and_phase(self.current_turn, phase_name)
        
        # Trova veggente vivo
        seer = None
        for name, player in self.players.items():
            if player.role == Role.VEGGENTE and player.is_alive:
                seer = player
                break
        
        if not seer:
            return
        
        # Candidati: vivi non già investigati
        candidates = [
            n for n in self.get_alive_players()
            if n != seer.name and n not in seer.known_roles
        ]
        
        if not candidates:
            self.transcript.add_system_message(f"{seer.name} ha già investigato tutti")
            return
        
        game_state = self.get_game_state()
        target, reasoning = seer.generate_seer_choice(
            game_state=game_state,
            current_phase=phase_name,
            candidates=candidates,
        )
        
        if target and target in self.players:
            revealed_role = self.players[target].role
            seer.known_roles[target] = revealed_role
            
            # Mostra a terminale la scelta del veggente
            seer_emoji = get_role_emoji(Role.VEGGENTE)
            target_emoji = get_role_emoji(revealed_role)
            print(f"\n{seer_emoji} VEGGENTE ({seer.name}) investiga {target}")
            print(f"🔍 Risultato: {target} è un {target_emoji}{revealed_role.value}!")
            
            # Salva pensiero nel transcript (include motivazione se presente)
            msg = f"Ho investigato {target}: è un {target_emoji}{revealed_role.value}!"
            if reasoning:
                msg = f"{reasoning} -> {msg}"
            self.transcript.add_inner_dialogue(seer.name, msg)
            seer.update_scratchpad(f"Scoperto: {target} è {target_emoji}{revealed_role.value}")
    
    def resolve_night(self) -> Optional[str]:
        """Risolve la notte."""
        # Header alba
        print(f"\n{'='*50}")
        print(f"🌅 ALBA - Turno {self.current_turn}")
        print(f"{'='*50}")
        
        if not self.wolf_target:
            print("😌 Nessuna vittima questa notte.")
            return None
        
        # Uccidi la vittima
        victim = self.wolf_target
        victim_role = self._kill_player(victim)
        
        event = f"Notte {self.current_turn}: {victim} ucciso dai lupi (era {victim_role.value})"
        self.add_public_event(event)
        
        self.transcript.add_system_message(f"⚰️ All'alba si trova il corpo di {victim}. Era un {victim_role.value}.")
        
        self.wolf_target = None
        return victim
    
    # =========================================================================
    # SCRATCHPAD EDIT (fine giornata)
    # =========================================================================
    
    def edit_all_scratchpads(self):
        """Fa editare lo scratchpad a tutti i giocatori vivi (fine giornata)."""
        game_state = self.get_game_state()
        
        for name in self.get_alive_players():
            player = self.players[name]
            if player.scratchpad:  # Solo se hanno qualcosa
                player.edit_scratchpad(game_state)
    
    # =========================================================================
    # FLUSSO PRINCIPALE
    # =========================================================================
    
    def run_day(self) -> bool:
        """Esegue un giorno completo."""
        self.run_day_discussion()
        
        if self.check_game_over()[0]:
            return False
        
        self.run_day_voting()
        
        # Edit scratchpad a fine giornata (prima della notte)
        self.edit_all_scratchpads()
        
        return not self.check_game_over()[0]
    
    def run_night(self) -> bool:
        """Esegue una notte completa."""
        self.run_night_wolf_discussion()
        self.run_night_wolf_voting()
        self.run_night_seer()
        self.resolve_night()
        
        return not self.check_game_over()[0]
    
    def run_game(self) -> str:
        """Esegue una partita completa."""
        print("\n" + "="*60)
        print("🐺 LUPUS IN FABULA - INIZIO PARTITA 🐺")
        print("="*60)
        
        # Notte 0
        self.current_turn = 0
        self.run_night()
        
        # Check early stop
        if self.config.max_turns is not None and self.current_turn >= self.config.max_turns:
            self.transcript.add_system_message(f"⏹️ EARLY STOP: limite {self.config.max_turns} turni")
            self.game_over = True
        
        while not self.game_over:
            # Giorno
            self.current_turn += 1
            if not self.run_day():
                break
            
            if self.config.max_turns is not None and self.current_turn >= self.config.max_turns:
                self.transcript.add_system_message(f"⏹️ EARLY STOP: limite {self.config.max_turns} turni")
                self.game_over = True
                break
            
            # Notte
            if not self.run_night():
                break
        
        # Fine partita
        self._update_transcript_players_info()
        
        # Annuncio finale
        print("\n" + "="*60)
        if self.winner == "lupi":
            print("🐺🐺🐺 I LUPI HANNO VINTO! 🐺🐺🐺")
        else:
            print("🌾🌾🌾 IL VILLAGGIO HA VINTO! 🌾🌾🌾")
        print("="*60)
        
        # Genera report finale
        report = self.transcript.generate_final_report(self.winner)
        
        # Statistiche finali
        stats = self.transcript.get_statistics()
        print(f"\n📊 Statistiche partita:")
        print(f"   Turni: {self.current_turn}")
        print(f"   Fasi: {stats.get('num_phases', 0)}")
        print(f"   Eventi: {stats.get('total_events', 0)}")
        print(f"\n📁 Dati salvati in: {self.transcript.get_game_directory()}")
        
        return self.winner
