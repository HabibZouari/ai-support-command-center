"""Unit tests for the agent layer. No network: the LLM and vector store are stubbed."""

from unittest.mock import MagicMock, patch

import pytest

from app.agents import billing_agent
from app.agents.orchestrator import build_agent_graph
from app.agents.quality_gate import (
    LOW_CONFIDENCE_THRESHOLD,
    quality_gate_node,
    quality_selector,
)
from app.agents.router_agent import DEFAULT_ROUTE, parse_router_output
from app.rag.chunking import build_chunk_records, chunk_text
from app.schemas.schemas import RetrievedChunk


# ---------- router parsing ----------
@pytest.mark.parametrize(
    "raw",
    [
        '{"category": "billing", "route": "billing", "reasoning": "x"}',
        '```json\n{"category": "billing", "route": "billing"}\n```',
        'Sure! Here you go: {"category": "billing", "route": "BILLING"} hope it helps',
    ],
)
def test_router_parses_fenced_and_noisy_json(raw):
    assert parse_router_output(raw) == ("billing", "billing")


def test_router_rejects_unknown_route():
    _, route = parse_router_output('{"category": "x", "route": "sales"}')
    assert route == DEFAULT_ROUTE


@pytest.mark.parametrize("raw", ["", "not json", None])
def test_router_raises_when_no_json(raw):
    with pytest.raises((ValueError, AttributeError)):
        parse_router_output(raw)


# ---------- quality gate ----------
def test_quality_gate_flags_low_confidence():
    state = quality_gate_node({"confidence_score": LOW_CONFIDENCE_THRESHOLD - 0.01})
    assert quality_selector(state) == "escalation"


def test_quality_gate_passes_confident_answer():
    state = quality_gate_node({"confidence_score": 0.9})
    assert quality_selector(state) == "end"


def test_quality_gate_does_not_re_escalate():
    state = quality_gate_node({"confidence_score": 0.0, "escalated": True})
    assert quality_selector(state) == "end"


# ---------- full graph wiring ----------
def _run_graph(route: str, confidence: float) -> dict:
    def router(state):
        return {**state, "route": route}

    def specialist(name):
        def node(state):
            return {
                **state,
                "final_response": "answer",
                "agent_used": name,
                "confidence_score": confidence,
                "escalated": False,
            }

        return node

    def escalation(state):
        return {**state, "agent_used": "escalation_agent", "escalated": True}

    with (
        patch("app.agents.orchestrator.router_node", router),
        patch("app.agents.orchestrator.knowledge_node", specialist("knowledge_agent")),
        patch("app.agents.orchestrator.support_node", specialist("support_agent")),
        patch("app.agents.orchestrator.billing_node", specialist("billing_agent")),
        patch("app.agents.orchestrator.escalation_node", escalation),
    ):
        graph = build_agent_graph()
        return graph.invoke({"ticket_id": "t1", "user_message": "hi", "trace": []})


@pytest.mark.parametrize(
    "route,agent",
    [
        ("knowledge", "knowledge_agent"),
        ("support", "support_agent"),
        ("billing", "billing_agent"),
    ],
)
def test_graph_routes_to_specialist_when_confident(route, agent):
    result = _run_graph(route, confidence=0.9)
    assert result["agent_used"] == agent
    assert result["escalated"] is False


def test_graph_escalates_on_low_confidence():
    result = _run_graph("knowledge", confidence=0.1)
    assert result["agent_used"] == "escalation_agent"
    assert result["escalated"] is True


def test_graph_escalation_route_skips_specialists():
    result = _run_graph("escalation", confidence=0.9)
    assert result["agent_used"] == "escalation_agent"


# ---------- billing tool guard ----------
def _run_billing(query: str) -> str:
    """Return the user prompt the billing agent sent to the LLM."""
    llm = MagicMock()
    llm.generate.return_value = ("ok", 5)
    retriever = MagicMock()
    retriever.retrieve.return_value = [
        RetrievedChunk(text="t", score=0.9, source="Refund Policy")
    ]
    retriever.format_context.return_value = "ctx"
    with (
        patch.object(billing_agent, "get_llm_client", return_value=llm),
        patch.object(billing_agent, "get_retriever", return_value=retriever),
    ):
        billing_agent.billing_node({"ticket_id": "t1", "user_message": query})
    return llm.generate.call_args.kwargs["user_prompt"]


def test_billing_files_refund_only_for_explicit_amount():
    prompt = _run_billing("Please refund the $19.99 I was charged")
    assert "create_refund_request" in prompt
    assert "$19.99" in prompt


def test_billing_policy_question_does_not_file_refund():
    prompt = _run_billing("What is your refund policy? It has been 3 days")
    assert "create_refund_request" not in prompt
    assert "check_recent_payment" in prompt


# ---------- chunking ----------
def test_short_text_is_a_single_chunk():
    assert chunk_text("hello   world") == ["hello world"]


def test_long_text_chunks_overlap():
    words = [f"w{i}" for i in range(1200)]
    chunks = chunk_text(" ".join(words), chunk_size=500, chunk_overlap=75)
    assert len(chunks) == 3
    assert chunks[0].split()[-75:] == chunks[1].split()[:75]


def test_chunk_records_carry_metadata():
    records = build_chunk_records("Title", "some content", category="billing")
    assert records[0]["metadata"]["title"] == "Title"
    assert records[0]["metadata"]["category"] == "billing"
