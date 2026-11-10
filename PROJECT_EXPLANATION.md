# AI Customer Support Command Center — Project Explanation

## 1. What This Project Is

This is an **enterprise-grade AI customer support platform** that automatically handles incoming support messages using a multi-agent pipeline. When a customer sends a message, the system classifies it, routes it to the appropriate specialist AI agent, retrieves relevant knowledge base context, generates a grounded response, and auto-escalates to a human when confidence is low — all without manual intervention.

The architecture demonstrates a production-ready stack combining **LangGraph multi-agent orchestration**, **Retrieval-Augmented Generation (RAG)** over Pinecone, **Groq-hosted LLMs** for low-latency inference, **MLflow** for experiment tracking, and full **CI/CD with Kubernetes deployment**.

---

## 2. Architecture Overview

```
                        +—————————————————————————————+
                        |     Streamlit Frontend      |
                        |       (port 8501)           |
                        +————————————┬————————————————+
                                     | HTTP (httpx)
                        +————————————▼————————————————+
                        |     FastAPI Application     |
                        |     POST /api/v1/chat       |
                        |   JWT Auth · /metrics       |
                        +————————————┬————————————————+
                                     |
             +———————————————————————▼————————————————————————+
             |              LangGraph State Machine            |
             |                                                 |
             |  ┌──────────────────────────────────────────┐  |
             |  │            Router Agent                  │  |
             |  │   (LLM-based intent classifier)          │  |
             |  └────┬──────────┬───────────┬──────────┬───┘  |
             |       │          │           │          │       |
             |  ┌────▼──┐ ┌────▼───┐ ┌────▼────┐ ┌───▼─────┐|
             |  │Knowl- │ │Support │ │Billing  │ │Escalat- ││
             |  │edge   │ │Agent   │ │Agent    │ │ion      ││
             |  │Agent  │ │RAG +   │ │RAG +    │ │Agent    ││
             |  │(RAG)  │ │Tools   │ │Tools    │ │(human)  ││
             |  └────┬──┘ └────┬───┘ └────┬────┘ └────┬────┘|
             |       └─────────┼──────────┘           │      |
             |            ┌────▼────────┐             │      |
             |            │Quality Gate │             │      |
             |            │conf < 0.5?  │             │      |
             |            └────┬────────┘             │      |
             |        ok ──────▼   low conf ──────────▼      |
             |          [END]              [Escalation→END]  |
             +————————————————————————————————————————————————+
                   │              │              │
          +————————▼———+  +——————▼—————+  +—————▼————————+
          │  MySQL 8   │  │ Pinecone   │  │ MLflow       │
          │ users,     │  │ Vector DB  │  │ Tracking     │
          │ tickets,   │  │ (RAG)      │  │ Server       │
          │ messages   │  │            │  │              │
          +————————————+  +————————————+  +——————————————+
```

---

## 3. The Multi-Agent Workflow (LangGraph)

The heart of the system is an **orchestrator** (`app/agents/orchestrator.py`) that builds a **LangGraph `StateGraph`** — a directed graph where each node is an AI agent and edges define the control flow. The graph is compiled once and reused for every request.

### Nodes (Agents)

| Node | File | Purpose |
|---|---|---|
| **Router** | `router_agent.py` | Classifies user intent into a category (`billing`, `technical`, `account`, etc.) and selects a route (`knowledge`, `support`, `billing`, or `escalation`). Uses an LLM call with a structured JSON output prompt. |
| **Knowledge** | `knowledge_agent.py` | Answers factual/how-to questions. Retrieves top-5 chunks from Pinecone, formats them as context, and passes them to the LLM with a grounded-answering prompt. |
| **Support** | `support_agent.py` | Handles technical troubleshooting. Uses RAG (top-4 technical chunks) plus simulated tools (e.g., `check_account_status`) when keywords match. |
| **Billing** | `billing_agent.py` | Handles payment/refund/subscription queries. Uses RAG (top-4 billing chunks) plus simulated tools (`create_refund_request`, `check_subscription_plan`). |
| **Escalation** | `escalation_agent.py` | Produces an empathetic holding response and flags the ticket for human handoff. Does NOT try to solve the issue. |
| **Quality Gate** | `quality_gate.py` | A pass-through evaluation node — checks the **confidence score** from the preceding agent and decides whether to escalate. |

### Edges (Control Flow)

```
Entry → Router
Router →(conditional)→ Knowledge | Support | Billing | Escalation
Knowledge → Quality Gate
Support   → Quality Gate
Billing   → Quality Gate
Quality Gate →(conditional)→ END (if confidence OK) | Escalation (if low)
Escalation → END
```

### Confidence-Based Escalation

This is the key safety mechanism:

1. Each specialist agent (Knowledge, Support, Billing) computes a **confidence score** — the average semantic similarity score of the retrieved Pinecone chunks.
2. The **Quality Gate** compares this score against a threshold: `settings.similarity_threshold - 0.15` (default: `0.65 - 0.15 = 0.50`).
3. If confidence < 0.50 **and** the ticket hasn't already been escalated, the quality gate routes to the **Escalation Agent** instead of returning the response to the user.
4. The Escalation Agent generates a holding response and sets `escalated=True` on the state, which the API layer uses to update the ticket status to `ESCALATED`.

This ensures the system never returns a low-confidence hallucinated answer — it gracefully hands off to a human.

### Shared State (`AgentState`)

All agents read from and write to a single `TypedDict` object. Key fields:

| Field | Set By | Purpose |
|---|---|---|
| `user_message` | Caller | The incoming customer message |
| `route` | Router | Which specialist should handle it |
| `retrieved_context` | Specialist | RAG context from Pinecone |
| `final_response` | Specialist/Escalation | The text returned to the user |
| `confidence_score` | Specialist | Average retrieval similarity score |
| `escalated` | Escalation | Whether handed off to human |
| `trace` | All agents | Audit trail for debugging |
| `latency_ms` | Orchestrator | End-to-end pipeline timing |

---

## 4. Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **API** | FastAPI 0.115 + Uvicorn | REST API server |
| **Frontend** | Streamlit 1.40 | Browser-based command center UI |
| **Agentic AI** | LangGraph 0.2 | State-machine multi-agent orchestration |
| **LLM** | Groq API (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`) | Fast inference for all agents |
| **Vector DB** | Pinecone (serverless, cosine similarity) | RAG knowledge retrieval |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` (384-dim) | Local embedding model for queries and docs |
| **Database** | MySQL 8.0 via PyMySQL + SQLAlchemy 2.0 | Users, tickets, conversations, messages, agent runs |
| **Auth** | JWT (python-jose HS256) + bcrypt (passlib) | Stateless authentication |
| **MLOps** | MLflow 2.17 | Agent run tracking, heuristic quality metrics, offline evaluation |
| **Observability** | structlog (JSON logs), Prometheus `/metrics`, Grafana | Structured logging and metrics |
| **Containerization** | Docker multi-stage build, docker-compose | Local and production deployment |
| **CI/CD** | GitHub Actions | Lint → Test → Eval gate → Build → Push → K8s deploy |
| **Orchestration** | Kubernetes (Deployment, Service, HPA, Ingress) | Production scaling |

---

## 5. Data Flow — Full Request Lifecycle

Here is the complete journey of a single customer message:

1. **User sends message** → `POST /api/v1/chat` with JWT token and `{ticket_id, message}`.

2. **Auth check** → `deps.py` decodes the JWT, looks up the user in MySQL.

3. **Ticket lookup** → The endpoint fetches the ticket and its conversation history from MySQL.

4. **User message persisted** → Saved as a `Message` row in the `messages` table.

5. **Conversation history built** → Last 10 messages are formatted as `[{role, content}, ...]`.

6. **Agent pipeline invoked** → `run_agent_pipeline(ticket_id, message, history)`:
   - a) **Router Agent** → LLM classifies intent, returns `{category, route}`.
   - b) **Specialist Agent** (based on route):
     - Embeds the query using `all-MiniLM-L6-v2`.
     - Queries Pinecone for top-k similar chunks (with optional category filter).
     - Optionally invokes simulated tools (account lookup, refund request, etc.).
     - Calls Groq LLM with retrieved context + tool output.
     - Returns response + confidence score (average chunk similarity).
   - c) **Quality Gate** → Checks confidence. If < 0.50, reroutes to Escalation.
   - d) **Escalation Agent** (if triggered) → Generates empathetic holding response.

7. **Agent response persisted** → Saved as an `AGENT`-type `Message` in MySQL.

8. **Ticket status updated** → To `IN_PROGRESS` or `ESCALATED`.

9. **MLflow logging** (background task) → Logs agent name, confidence, latency, heuristic quality metrics (response length, groundedness, unsafe patterns), and prompt version.

10. **Response returned** → `ChatResponse` JSON with: response text, agent used, confidence, sources, escalation flag, latency.

---

## 6. Key Modules Explained

### RAG Pipeline (`app/rag/`)

- **`embeddings.py`** — Wraps `SentenceTransformer` for single/batch embedding. Cached singleton.
- **`chunking.py`** — Splits documents into overlapping word-based chunks (500 words, 75-word overlap).
- **`vector_store.py`** — Wraps Pinecone: index creation, upsert, similarity search with metadata filtering.
- **`retriever.py`** — The interface agents call: retrieves top-k chunks, formats them into numbered context blocks.

### Services (`app/services/`)

- **`llm_client.py`** — Groq API wrapper with retry logic (3 attempts, exponential backoff) and automatic fallback to a smaller model.
- **`evaluation.py`** — Heuristic quality metrics (response length, word-overlap groundedness, unsafe pattern detection) plus LLM-as-judge scoring for offline batches.
- **`mlflow_logger.py`** — Logs each agent invocation as an MLflow run: core metrics + heuristic scores + prompt version tag. Fails silently so observability never breaks user-facing requests.
- **`prompt_registry.py`** — Versioned registry of all agent system prompts. Enables correlating prompt changes with quality shifts in MLflow.

### API Routes (`app/api/`)

- **`auth_routes.py`** — `/register` and `/login` (JWT issuance).
- **`ticket_routes.py`** — CRUD for support tickets.
- **`chat_routes.py`** — The main endpoint: runs the full agent pipeline.
- **`kb_routes.py`** — Admin-only document ingestion into Pinecone.
- **`health_routes.py`** — K8s liveness (`/health`) and readiness (`/ready`, checks DB).

---

## 7. Database Schema (MySQL)

Five tables:

| Table | Description |
|---|---|
| `users` | User accounts (email, hashed password, admin flag) |
| `tickets` | Support tickets (subject, status, priority, category) |
| `conversations` | 1:1 with tickets; groups messages |
| `messages` | Individual chat messages (user, agent, human_agent, system) |
| `agent_runs` | Observability: each agent invocation's input, output, latency, confidence |

---

## 8. Frontend (Streamlit)

The Streamlit app (`frontend/streamlit_app.py`) is a single-page command center with four tabs:

1. **Access** — Register and login (stores JWT in session state)
2. **Tickets** — Create tickets and view the ticket queue
3. **Agent Chat** — Send messages through the full agent pipeline and see responses
4. **Knowledge Base** — Ingest documents into Pinecone (admin only)

It communicates with the FastAPI backend via `httpx` HTTP calls to `API_BASE_URL` (default: `http://localhost:8000`).

---

## 9. MLOps & Evaluation

### Live Metrics (every request)
- Response length score
- Word-overlap groundedness score
- Unsafe pattern detection (`"as an AI"`, `"I don't know"`)
- Confidence, latency, escalation flag

### Offline Evaluation (`scripts/run_offline_eval.py`)
- Runs 8 golden queries through the full pipeline
- Scores routing accuracy, keyword coverage, confidence, latency
- Logs aggregate results to MLflow
- CI gate: exits non-zero if routing accuracy < 70%
