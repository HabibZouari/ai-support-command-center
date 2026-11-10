import os

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def api_request(method: str, path: str, token: str | None = None, json: dict | list | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.request(method, f"{API_BASE_URL}{path}", headers=headers, json=json)
        if response.status_code >= 400:
            detail = response.json().get("detail", response.text)
            st.error(f"{response.status_code}: {detail}")
            return None
        return response.json()
    except httpx.HTTPError as exc:
        st.error(f"API connection failed: {exc}")
        return None


st.set_page_config(page_title="AI Support Platform", page_icon="AI", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

    :root {
        --ink: #172033;
        --muted: #667085;
        --line: #d9e2ef;
        --blue: #1e6bff;
        --teal: #00a98f;
        --navy: #10213d;
    }

    html, body, [class*="css"] {
        font-family: "Manrope", sans-serif;
    }

    .stApp {
        color: var(--ink);
        background:
            radial-gradient(circle at 8% 12%, rgba(30, 107, 255, 0.16), transparent 28%),
            radial-gradient(circle at 88% 8%, rgba(0, 169, 143, 0.14), transparent 28%),
            linear-gradient(135deg, #f7fbff 0%, #eef4f8 45%, #f9fbff 100%);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #10213d 0%, #163457 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    section[data-testid="stSidebar"] * {
        color: #f5f8ff !important;
    }

    section[data-testid="stSidebar"] textarea {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
    }

    .block-container {
        padding-top: 1.25rem;
        max-width: 1240px;
    }

    .hero {
        position: relative;
        overflow: hidden;
        padding: 28px 30px;
        border: 1px solid rgba(16, 33, 61, 0.08);
        border-radius: 18px;
        background:
            linear-gradient(120deg, rgba(16, 33, 61, 0.96), rgba(30, 107, 255, 0.86)),
            repeating-linear-gradient(45deg, rgba(255,255,255,0.08) 0 1px, transparent 1px 18px);
        box-shadow: 0 24px 60px rgba(16, 33, 61, 0.16);
    }

    .hero h1 {
        margin: 0 0 8px 0;
        color: #ffffff;
        font-size: 2.25rem;
        letter-spacing: 0;
        line-height: 1.1;
    }

    .hero p {
        color: rgba(255, 255, 255, 0.82);
        margin: 0;
        max-width: 760px;
        font-size: 1rem;
    }

    .hero-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin-top: 22px;
    }

    .metric-card {
        border-radius: 14px;
        padding: 16px;
        background: rgba(255, 255, 255, 0.13);
        border: 1px solid rgba(255, 255, 255, 0.18);
    }

    .metric-card span {
        display: block;
        color: rgba(255, 255, 255, 0.7);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    .metric-card strong {
        display: block;
        margin-top: 6px;
        color: #ffffff;
        font-size: 1.05rem;
    }

    .section-card {
        padding: 22px;
        border: 1px solid rgba(16, 33, 61, 0.08);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.9);
        box-shadow: 0 14px 38px rgba(16, 33, 61, 0.08);
        margin-bottom: 16px;
    }

    .section-card h3 {
        margin: 0 0 6px 0;
        color: var(--navy);
        font-size: 1.12rem;
    }

    .section-card p {
        margin: 0 0 16px 0;
        color: var(--muted);
    }

    .agent-response {
        padding: 18px;
        border-left: 5px solid var(--teal);
        border-radius: 14px;
        background: #eefbf8;
        color: #10372f;
        box-shadow: inset 0 0 0 1px rgba(0, 169, 143, 0.12);
    }

    div[data-testid="stTabs"] button {
        font-weight: 800;
        color: var(--navy);
    }

    .stButton > button, .stFormSubmitButton > button {
        border: 0;
        border-radius: 10px;
        background: linear-gradient(135deg, var(--blue), #104fd2);
        color: white;
        font-weight: 800;
        min-height: 42px;
        box-shadow: 0 10px 22px rgba(30, 107, 255, 0.2);
    }

    .stTextInput input, .stTextArea textarea {
        border-radius: 10px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.86);
        color: #172033 !important;
    }

    .stTextInput label, .stTextArea label, .stSelectbox label {
        color: #10213d !important;
        font-weight: 600;
    }

    .status-pill {
        display: inline-flex;
        padding: 8px 10px;
        border-radius: 999px;
        background: rgba(0, 169, 143, 0.12);
        color: #006b5c;
        font-weight: 800;
        font-size: 0.82rem;
        border: 1px solid rgba(0, 169, 143, 0.18);
    }

    @media (max-width: 760px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
        .hero h1 {
            font-size: 1.65rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "token" not in st.session_state:
    st.session_state.token = ""
if "ticket_id" not in st.session_state:
    st.session_state.ticket_id = ""

token_status = "Authenticated" if st.session_state.token else "Guest session"
ticket_status = st.session_state.ticket_id or "No active ticket"

st.markdown(
    f"""
    <div class="hero">
        <h1>AI Customer Support Command Center</h1>
        <p>Operate the support workflow from one place: authenticate, create tickets, run the agent graph, and ingest knowledge documents into the RAG store.</p>
        <div class="hero-grid">
            <div class="metric-card"><span>Backend</span><strong>{API_BASE_URL}</strong></div>
            <div class="metric-card"><span>Session</span><strong>{token_status}</strong></div>
            <div class="metric-card"><span>Active Ticket</span><strong>{ticket_status}</strong></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

with st.sidebar:
    st.markdown("### Control Panel")
    st.markdown(f'<div class="status-pill">{token_status}</div>', unsafe_allow_html=True)
    st.write("")
    token_input = st.text_area("JWT token", value=st.session_state.token, height=120)
    if token_input != st.session_state.token:
        st.session_state.token = token_input.strip()

    if st.button("Clear session"):
        st.session_state.token = ""
        st.session_state.ticket_id = ""
        st.rerun()


auth_tab, ticket_tab, chat_tab, kb_tab = st.tabs(["Access", "Tickets", "Agent Chat", "Knowledge Base"])

with auth_tab:
    register_col, login_col = st.columns(2)

    with register_col:
        st.markdown('<div class="section-card"><h3>Create Operator Account</h3><p>Register a user profile for ticket and chat workflows.</p>', unsafe_allow_html=True)
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            full_name = st.text_input("Full name")
            password = st.text_input("Password", type="password", key="register_password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            result = api_request(
                "POST",
                "/api/v1/auth/register",
                json={"email": email, "full_name": full_name, "password": password},
            )
            if result:
                st.success("User registered")
                st.json(result)
        st.markdown("</div>", unsafe_allow_html=True)

    with login_col:
        st.markdown('<div class="section-card"><h3>Secure Login</h3><p>Sign in and load the JWT token into this frontend session.</p>', unsafe_allow_html=True)
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")
        if submitted:
            result = api_request("POST", "/api/v1/auth/login", json={"email": email, "password": password})
            if result:
                st.session_state.token = result["access_token"]
                st.success("Logged in")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

with ticket_tab:
    create_col, list_col = st.columns([0.9, 1.1])
    with create_col:
        st.markdown('<div class="section-card"><h3>Create Ticket</h3><p>Start a support case and attach the first customer message.</p>', unsafe_allow_html=True)
        with st.form("ticket_form"):
            subject = st.text_input("Subject", value="Refund policy")
            initial_message = st.text_area("Initial message", value="I want to know the refund policy.")
            submitted = st.form_submit_button("Create ticket")
        if submitted:
            result = api_request(
                "POST",
                "/api/v1/tickets",
                token=st.session_state.token,
                json={"subject": subject, "initial_message": initial_message},
            )
            if result:
                st.session_state.ticket_id = result["id"]
                st.success("Ticket created")
                st.json(result)
        st.markdown("</div>", unsafe_allow_html=True)

    with list_col:
        st.markdown('<div class="section-card"><h3>Ticket Queue</h3><p>Review tickets created by the active user.</p>', unsafe_allow_html=True)
        if st.button("Load tickets"):
            result = api_request("GET", "/api/v1/tickets", token=st.session_state.token)
            if result is not None:
                st.dataframe(result, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

with chat_tab:
    st.markdown('<div class="section-card"><h3>Agent Chat Console</h3><p>Send a message through the LangGraph support pipeline.</p>', unsafe_allow_html=True)
    ticket_id = st.text_input("Ticket ID", value=st.session_state.ticket_id)
    message = st.text_area("Message", value="Can you summarize the refund policy?")
    if st.button("Send message"):
        result = api_request(
            "POST",
            "/api/v1/chat",
            token=st.session_state.token,
            json={"ticket_id": ticket_id, "message": message},
        )
        if result:
            st.success("Agent response")
            st.markdown(f'<div class="agent-response">{result["response"]}</div>', unsafe_allow_html=True)
            st.json(result)
    st.markdown("</div>", unsafe_allow_html=True)

with kb_tab:
    st.markdown('<div class="section-card"><h3>Knowledge Base Ingestion</h3><p>Push policy or support content into the RAG vector store. Admin token required.</p>', unsafe_allow_html=True)
    st.warning("This endpoint requires an admin token.")
    with st.form("kb_form"):
        title = st.text_input("Title", value="Refund Policy")
        category = st.text_input("Category", value="billing")
        content = st.text_area("Content", value="Customers can request a refund within 30 days of purchase.")
        source = st.text_input("Metadata source", value="streamlit")
        submitted = st.form_submit_button("Ingest document")
    if submitted:
        result = api_request(
            "POST",
            "/api/v1/knowledge-base/ingest",
            token=st.session_state.token,
            json={
                "title": title,
                "content": content,
                "category": category,
                "metadata": {"source": source},
            },
        )
        if result:
            st.success("Document ingested")
            st.json(result)
    st.markdown("</div>", unsafe_allow_html=True)
