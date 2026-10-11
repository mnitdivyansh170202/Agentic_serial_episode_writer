# Please review the Decisions.md file for information about the Decisions made while development.

# Serial Story Agent

Runnable prototype for the 200-episode serial-story assignment.

## Includes

- 200-episode hierarchical arc planning
- Episode-by-episode planning and writing
- Structured Story Bible / canon facts / plot threads via episode state
- ChromaDB semantic retrieval for older episode memories
- ChromaDB historical retrieval with episode-number filtering
- Episode crux extraction
- LangGraph StateGraph orchestration
- FastAPI backend
- Streamlit frontend
- SQLite persistence and resume
- Human arc approval
- Episode approve/edit/reject
- Persistent narrative feedback
- Retroactive change + impact analysis + downstream replay
- Token/reasoning-token/cost logging
- Deterministic word-count checks plus LLM continuity checks
- Explicit failure-mode documentation

## Architecture

Streamlit -> FastAPI -> LangGraph -> OpenAI GPT -> SQLite

The model defaults to `gpt-5.6-sol`; set `OPENAI_MODEL` in `.env` if another
model is available to your API account.

## Setup

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Put your API key in `.env`.

Run backend:

```bash
uvicorn backend.main:app --reload --port 8000
```

Run frontend in another terminal:

```bash
streamlit run frontend/app.py
```

Or use `run_backend.bat` / `run_frontend.bat` on Windows.

## Suggested evaluation demo

1. Create the delivery-rider premise.
2. Generate the full 200-episode arc.
3. Approve it.
4. Generate several episodes sequentially.
5. Add: "Slow down the romance between Arjun and Meera."
6. Generate another episode and show that the decision is persisted.
7. Edit an earlier episode/fact using Retroactive Change.
8. Show impact analysis and sequential downstream regeneration.
9. Restart the backend and show that SQLite retains the story.
10. Open Observability to show per-node token/cost records.

## Production extension

The demo uses SQLite as source of truth and ChromaDB for historical semantic retrieval.
The Chroma collection uses Chroma's default embedding function; first use may download its embedding model.
For production, add explicit revision snapshots, migration tooling, stronger fact conflict resolution,
and automated regression tests for retroactive replay.

The canonical story state should remain structured and authoritative; vector
retrieval should be a supporting historical-memory mechanism.
