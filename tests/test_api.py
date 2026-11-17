"""API tests against an in-memory SQLite DB, with the agent pipeline stubbed."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import chat_routes
from app.api.auth_routes import router as auth_router
from app.api.chat_routes import router as chat_router
from app.api.ticket_routes import router as ticket_router
from app.db.models import AgentRun
from app.db.session import Base, get_db


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    app = FastAPI()
    for r in (auth_router, ticket_router, chat_router):
        app.include_router(r)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), Session
    Base.metadata.drop_all(engine)


def _auth_headers(client: TestClient) -> dict:
    creds = {"email": "jane@example.com", "full_name": "Jane", "password": "s3cretpass"}
    assert client.post("/api/v1/auth/register", json=creds).status_code == 201
    token = client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fake_pipeline(**kwargs):
    return {
        "final_response": "Refunds are available within 30 days.",
        "agent_used": "billing_agent",
        "confidence_score": 0.8,
        "escalated": False,
        "sources": ["Refund Policy"],
        "latency_ms": 12,
        "category": "billing",
    }


def test_register_rejects_duplicate_email_and_overlong_password(client_and_session):
    client, _ = client_and_session
    _auth_headers(client)
    dup = {"email": "jane@example.com", "full_name": "J", "password": "s3cretpass"}
    assert client.post("/api/v1/auth/register", json=dup).status_code == 400
    long_pw = {"email": "b@example.com", "full_name": "B", "password": "x" * 73}
    assert client.post("/api/v1/auth/register", json=long_pw).status_code == 422


def test_login_with_wrong_password_is_401(client_and_session):
    client, _ = client_and_session
    _auth_headers(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "jane@example.com", "password": "wrong-pass"},
    )
    assert resp.status_code == 401


def test_tickets_require_auth(client_and_session):
    client, _ = client_and_session
    assert client.get("/api/v1/tickets").status_code == 401


def test_chat_persists_run_and_updates_ticket(client_and_session, monkeypatch):
    client, Session = client_and_session
    monkeypatch.setattr(chat_routes, "run_agent_pipeline", _fake_pipeline)
    monkeypatch.setattr(chat_routes, "log_agent_run", lambda **kw: None)
    headers = _auth_headers(client)

    ticket = client.post(
        "/api/v1/tickets",
        json={"subject": "Refund", "initial_message": "hello"},
        headers=headers,
    ).json()
    resp = client.post(
        "/api/v1/chat",
        json={"ticket_id": ticket["id"], "message": "refund policy?"},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["agent_used"] == "billing_agent"

    # one AgentRun row written, ticket moved to in_progress with a category
    with Session() as db:
        runs = db.query(AgentRun).all()
        assert len(runs) == 1 and runs[0].agent_name == "billing_agent"
    updated = client.get(f"/api/v1/tickets/{ticket['id']}", headers=headers).json()
    assert updated["status"] == "in_progress"
    assert updated["category"] == "billing"


def test_chat_returns_503_when_pipeline_fails(client_and_session, monkeypatch):
    client, _ = client_and_session

    def boom(**kwargs):
        raise RuntimeError("groq down")

    monkeypatch.setattr(chat_routes, "run_agent_pipeline", boom)
    headers = _auth_headers(client)
    ticket = client.post(
        "/api/v1/tickets",
        json={"subject": "s", "initial_message": "m"},
        headers=headers,
    ).json()

    resp = client.post(
        "/api/v1/chat",
        json={"ticket_id": ticket["id"], "message": "hi"},
        headers=headers,
    )
    assert resp.status_code == 503


def test_users_cannot_chat_on_other_users_tickets(client_and_session, monkeypatch):
    client, _ = client_and_session
    monkeypatch.setattr(chat_routes, "run_agent_pipeline", _fake_pipeline)
    owner = _auth_headers(client)
    ticket = client.post(
        "/api/v1/tickets", json={"subject": "s", "initial_message": "m"}, headers=owner
    ).json()

    other = {"email": "eve@example.com", "full_name": "Eve", "password": "s3cretpass"}
    client.post("/api/v1/auth/register", json=other)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": other["email"], "password": other["password"]},
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/chat",
        json={"ticket_id": ticket["id"], "message": "hi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
