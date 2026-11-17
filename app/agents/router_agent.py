"""
Router Agent — the entry point of the multi-agent graph.
Classifies the user's intent/category and decides which downstream
specialized agent should handle the request.
"""

import json
import re

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.services.llm_client import get_llm_client

logger = get_logger(__name__)

ROUTER_SYSTEM_PROMPT = """You are a routing classifier for a customer support system.
Given a user's message, classify it into exactly one category and one route.

Categories: billing, technical, account, product_info, complaint, general

Routes (choose based on category and complexity):
- "knowledge": factual questions answerable from documentation (how-to, product info, policies)
- "support": account/technical issues needing troubleshooting steps
- "billing": payment, refund, subscription, invoice issues
- "escalation": angry/frustrated customers, legal threats, repeated unresolved issues, or anything explicitly requesting a human

Respond ONLY with valid JSON in this exact format, nothing else:
{"category": "...", "route": "...", "reasoning": "short reason"}
"""


VALID_ROUTES = {"knowledge", "support", "billing", "escalation"}
DEFAULT_ROUTE = "knowledge"


def parse_router_output(raw: str) -> tuple[str, str]:
    """Extract (category, route) from the LLM output, falling back to safe defaults.

    Tolerates markdown fences / extra prose around the JSON and rejects routes
    the graph has no node for (which would otherwise crash the conditional edge).
    """
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        raise ValueError("no JSON object in router output")
    parsed = json.loads(match.group(0))
    category = str(parsed.get("category", "general"))
    route = str(parsed.get("route", DEFAULT_ROUTE)).strip().lower()
    if route not in VALID_ROUTES:
        logger.warning("router_invalid_route", route=route)
        route = DEFAULT_ROUTE
    return category, route


def router_node(state: AgentState) -> AgentState:
    """Classify the incoming message and set the route for the graph."""
    llm = get_llm_client()
    user_message = state["user_message"]

    history_snippet = ""
    if state.get("conversation_history"):
        last_turns = state["conversation_history"][-3:]
        history_snippet = "\n".join(f"{t['role']}: {t['content']}" for t in last_turns)

    prompt = (
        f"Conversation so far:\n{history_snippet}\n\nLatest message: {user_message}"
    )

    raw_response, latency = llm.generate(
        system_prompt=ROUTER_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
        max_tokens=400,
    )

    try:
        category, route = parse_router_output(raw_response)
    except (ValueError, AttributeError):  # JSONDecodeError is a ValueError
        logger.warning("router_parse_failed", raw=raw_response)
        category, route = "general", DEFAULT_ROUTE

    trace = state.get("trace", [])
    trace.append(
        {
            "agent": "router",
            "action": "classify",
            "detail": f"category={category}, route={route}",
        }
    )

    logger.info("router_decision", category=category, route=route, latency_ms=latency)

    return {
        **state,
        "category": category,
        "route": route,
        "trace": trace,
    }


def route_selector(state: AgentState) -> str:
    """Conditional-edge function: returns the next node name based on state.route."""
    return state.get("route", "knowledge")
