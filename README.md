# Lupus in AI 🐺

Simulatore di **Lupus in Fabula** (Mafia/Werewolf) dove gli agenti sono controllati da Large Language Models via OpenRouter.

## 🎮 Come funziona

Il gioco simula una partita di Lupus in Fabula con 10 giocatori (configurabili):
- **3 Lupi** 🐺 - Devono eliminare tutti i villici
- **1 Veggente** 🔮 - Può scoprire un ruolo ogni notte
- **1 Prostituta** 💋 - Può proteggere un giocatore ogni notte (ma non la stessa persona due volte!)
- **5 Contadini** 🌾 - Devono scoprire ed eliminare i lupi

**Ogni giocatore È il modello LLM** - il nome del giocatore è lo short name del modello (es. "GPT-4o", "Claude-3.5", "Llama-70B").

## 📁 Struttura del progetto

```
lupus-in-ai/
├── main.py              # Entry point principale
├── game_engine.py       # Motore di gioco (stato, fasi, flusso)
├── player_agent.py      # Wrapper LLM con memoria locale
├── transcript_manager.py # Gestione chat e transcript
├── config.py            # Configurazione e costanti
├── requirements.txt     # Dipendenze Python
└── transcripts/         # Directory con i transcript delle partite
    └── game_YYYYMMDD_HHMMSS/  # Una directory per partita
        ├── RESOCONTO_COMPLETO.md  # Resoconto leggibile
        └── game_data.json         # Dati completi in JSON
```

## 🚀 Setup

### 1. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 2. Configura la API Key di OpenRouter

Ottieni una API key da [OpenRouter](https://openrouter.ai/) e impostala come variabile d'ambiente:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

Oppure crea un file `.env`:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. Esegui il gioco

```bash
python main.py
```

## 🎯 Modalità di gioco

### Interattiva (default)
```bash
python main.py
```
Ti guida nella configurazione della partita.

### Singola partita
```bash
python main.py --mode single --players 10 --wolves 3
```

### Torneo
```bash
python main.py --mode tournament --games 10
```

### Opzioni
```
--mode        Modalità: single, tournament, interactive (default)
--games       Numero di partite per torneo (default: 5)
--players     Numero di giocatori (default: 10)
--wolves      Numero di lupi (default: 3)
--no-save     Non salvare i transcript
--list-models Mostra i modelli disponibili
```

## 🔧 Fasi di gioco

### Giorno
1. **Discussione**: I giocatori discutono pubblicamente
2. **Votazione**: Si vota per eliminare un sospetto (serve maggioranza)

### Notte
1. **Discussione Lupi**: I lupi si coordinano nella chat segreta
2. **Voto Lupi**: I lupi scelgono chi uccidere
3. **Veggente**: Il veggente scopre un ruolo
4. **Prostituta**: La prostituta sceglie chi proteggere

## 🤖 Modelli disponibili

- OpenAI GPT-4o, GPT-4o-mini
- Anthropic Claude 3.5 Sonnet, Claude 3 Haiku
- Google Gemini Pro 1.5, Gemini Flash 1.5
- Meta Llama 3.1 70B, Llama 3.1 8B
- Mistral Large, Mixtral 8x7B

## 📊 Transcript

Ogni partita crea una directory dedicata in `transcripts/game_TIMESTAMP/` contenente:
- `RESOCONTO_COMPLETO.md` - Resoconto leggibile in Markdown con:
  - Lista giocatori con ruoli e modelli
  - Cronologia completa degli eventi
  - Inner dialogues di ogni giocatore
  - Statistiche finali
- `game_data.json` - Dati completi in formato JSON

## 🔇 Sistema [PASS]

I giocatori possono scegliere di rimanere in silenzio usando il tag `[PASS]`:
- Utile per non attirare attenzione
- Strategia valida per osservare prima di parlare
- I messaggi [PASS] non vengono registrati nel transcript pubblico

## 🏗️ Architettura

### GameEngine
Mantiene lo stato della "verità" (chi è chi) e gestisce il flusso notte-giorno.

### PlayerAgent
Wrapper attorno all'LLM. Ogni agente ha:
- Il proprio ruolo e modello
- Uno scratchpad (memoria locale)
- Conoscenze scoperte (per il veggente)

### TranscriptManager
Gestisce tre tipi di "chat":
- **Pubblica**: Visibile a tutti
- **Lupi**: Visibile solo ai lupi
- **Inner dialogue**: Pensieri privati di ogni giocatore

## 📝 TODO

- [ ] Aggiungere più ruoli (cacciatore, cupido, etc.)
- [ ] Interfaccia web per seguire le partite
- [ ] Analisi post-partita delle strategie
- [ ] Supporto per giocatore umano
- [ ] Modalità "debate" con reasoning esplicito
