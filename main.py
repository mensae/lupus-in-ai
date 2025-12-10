"""
Lupus in AI - Entry point principale.
Simulatore di Lupus in Fabula con LLM.
"""
from config import GameConfig, AVAILABLE_MODELS
from game_engine import GameEngine


def print_banner():
    """Stampa il banner del gioco."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║     🐺  LUPUS IN AI - Lupus in Fabula con LLM  🐺            ║
    ║                                                               ║
    ║     Un simulatore di Lupus in Fabula dove gli agenti         ║
    ║     sono controllati da Large Language Models                 ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    """Entry point principale."""
    print_banner()
    
    # Configurazione default: 10 giocatori, 3 lupi, 1 veggente, 1 prostituta, 5 contadini
    config = GameConfig()
    config.validate()
    
    # Avvia la partita
    engine = GameEngine(config)
    engine.setup_game()
    engine.run_game()


if __name__ == "__main__":
    main()
