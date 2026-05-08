# SxQLear

> **Schema cognition platform. Analytical memory system. Dataset construction assistant.**

SxQLear is a local-first, AI-native environment for analysts and data professionals working with unfamiliar SQL databases. It helps you understand schemas, infer relationships, validate joins, and construct trustworthy datasets — with full provenance and explainability at every step.

---

## What problem does it solve?

When you receive credentials to an unfamiliar database, you face:

- 50–500+ undocumented tables with vague column names
- Hidden join paths that require hours of reverse engineering
- No way to know if your aggregates or cohorts are correct
- Context lost between sessions, tools, and team members
- Fear of silently wrong datasets in production analyses

SxQLear is not a SQL chatbot. It is an **analytical infrastructure layer** that:

1. Crawls and profiles your schema automatically
2. Infers candidate relationships using multi-signal analysis (structural, lexical, statistical, semantic)
3. Asks you to confirm or correct — with full evidence shown
4. Remembers every decision you make, persistently, per project
5. Constructs provenance-aware, annotated dataset plans and SQL

The result: you can trust what you're building.

---

## Architecture Overview

```
backend/
├── core/
│   ├── schema/        Schema crawling & graph construction
│   ├── inference/     Multi-signal relationship inference engine
│   ├── memory/        Persistent analytical memory (per project)
│   ├── validation/    Human-in-the-loop validation service
│   └── dataset/       Dataset plan construction & annotated SQL generation
├── models/            Pydantic domain models
├── db/                SQLite-backed local persistence (SQLAlchemy)
├── api/               FastAPI route handlers
├── config.py          Settings (pydantic-settings, .env support)
└── main.py            Application entry point

frontend/
├── src/
│   ├── views/         Connection, Schema, Inference, Validation, Memory, Dataset
│   ├── components/    Layout, Schema graph, Relationship cards, Validation queue
│   ├── stores/        Zustand state management
│   └── types/         TypeScript interfaces (mirrors backend models)
└── ...
```

**Inference pipeline (multi-signal, local-first):**
```
Structural signal  →  FK constraints + naming conventions   (weight: 0.45)
Lexical signal     →  Identifier similarity analysis        (weight: 0.30)
Statistical signal →  Value overlap (opt-in, sampled)       (weight: 0.15)
Semantic signal    →  Embedding similarity (opt-in)         (weight: 0.10)
LLM signal         →  Reasoning layer (optional, cloud)     (overlay)
```

Every relationship inference includes reasoning, evidence source, and confidence bounds.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### Optional: LLM integration

Create `backend/.env`:

```env
OPENAI_API_KEY=sk-...
ENABLE_LLM_INFERENCE=true
```

The system works fully without LLM keys. LLM reasoning is a supplementary layer only.

---

## Supported Databases

| Database   | Status     |
|------------|------------|
| PostgreSQL | Supported  |
| MySQL      | Supported  |
| SQLite     | Supported  |
| MSSQL      | Supported  |
| DuckDB     | Planned    |

---

## Design Principles

- **Transparency over magic.** Every inference has visible evidence and reasoning.
- **Human-in-the-loop.** AI proposes. Analyst confirms. Nothing is silently assumed.
- **Persistent cognition.** Your schema knowledge accumulates across sessions.
- **Local-first.** Works without any cloud dependency. Optional LLM calls use only metadata.
- **Provenance-first.** Every dataset plan records its assumptions, joins, and reasoning.

---

## Project Status

Early development (MVP). Core inference engine, schema crawling, and validation flows are functional.

---

## Contributors

| GitHub | Role |
|--------|------|
| [@Sw4ppleneel](https://github.com/Sw4ppleneel) | Creator |
| [@ReservedSnow673](https://github.com/ReservedSnow673) | Core contributor |
