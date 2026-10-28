import html
import json
import os
import uuid

import requests
import streamlit as st

APP_NAME = "AgentDesk"

# The backend address comes from an environment variable so Docker can change it later.
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

AVATARS = {"user": ":material/person:", "assistant": ":material/smart_toy:"}

# Each specialist is a tool of the Main Agent. Keys are the backend tool names.
AGENTS = {
    "analyze_requirements": ("📋", "Requirements Analyst", "Functional requirements, assumptions and acceptance criteria"),
    "review_security": ("🛡️", "Security Reviewer", "Security risks and recommended safeguards"),
    "plan_tests": ("🧪", "Test Planner", "Test cases for normal use, edge cases and failures"),
    "plan_implementation": ("🏗️", "Technical Lead", "Architecture and implementation approach"),
    "calculate": ("🧮", "Calculator Agent", "Adds numbers with a real Python tool"),
    "save_project_fact": ("💾", "Memory", "Saves lasting project facts to AutoGen ListMemory"),
}

EXAMPLE_PROMPTS = [
    "Plan a password reset feature",
    "Security risks of file uploads",
    "What is 25 + 17?",
    "My app uses Laravel and MySQL",
]

FLOW_CSS = """
<style>
.ad-flow{display:flex;flex-direction:column;color:inherit;margin:4px 0 8px}
.ad-row{display:flex;justify-content:center}
.ad-row .ad-node{width:100%;max-width:380px}
.ad-node{border:1px solid rgba(128,128,128,.28);background:rgba(128,128,128,.06);border-radius:12px;padding:8px 12px;min-width:0;transition:all .3s}
.ad-head{font-weight:600;font-size:.88rem;display:flex;align-items:center;gap:7px}
.ad-detail{font-size:.75rem;opacity:.72;margin-top:3px;line-height:1.35;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.ad-dot{width:8px;height:8px;border-radius:50%;background:rgba(128,128,128,.5);flex:none}
.ad-node.active{border-color:#4F46E5;animation:ad-glow 1.4s ease-in-out infinite}
.ad-node.active .ad-dot{background:#4F46E5;animation:ad-blink 1s ease-in-out infinite}
.ad-node.done{border-color:rgba(22,163,74,.65)}
.ad-node.done .ad-dot{background:#16a34a}
.ad-node.skipped{opacity:.38}
.ad-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:8px}
.ad-link{width:2px;height:16px;margin:3px auto;background:rgba(128,128,128,.35);border-radius:2px}
.ad-link.on{background:#4F46E5}
.ad-about .ad-detail{-webkit-line-clamp:unset}
.ad-brand{font-size:1.3rem;font-weight:700;letter-spacing:-.01em;margin-bottom:.25rem}
.ad-brand span{font-size:.8rem;font-weight:500;opacity:.6;margin-left:.5rem}
@keyframes ad-glow{0%,100%{box-shadow:0 0 0 1px rgba(79,70,229,.25)}50%{box-shadow:0 0 0 4px rgba(79,70,229,.22),0 0 16px rgba(79,70,229,.45)}}
@keyframes ad-blink{50%{opacity:.35}}
</style>
"""


def node_html(icon, title, state, detail):
    return (
        f'<div class="ad-node {state}"><div class="ad-head"><span class="ad-dot"></span>'
        f"{icon} {html.escape(title)}</div>"
        f'<div class="ad-detail">{html.escape(detail)}</div></div>'
    )


def render_flow(flow):
    """Build the agent flow diagram: request -> Main Agent -> specialists -> answer."""
    finished = flow["finished"]
    any_started = any(state != "idle" for state in flow["states"].values())

    if finished:
        coordinator_state, coordinator_detail = "done", "Combined the results into one answer"
    elif any(state == "done" for state in flow["states"].values()):
        coordinator_state, coordinator_detail = "active", "Reviewing specialist results..."
    else:
        coordinator_state, coordinator_detail = "active", "Reading the request and choosing specialists..."
    if flow["memory_read"]:
        coordinator_detail = f"Read {flow['memory_read']} saved fact(s) · " + coordinator_detail

    specialist_nodes = []
    for tool, (icon, name, _) in AGENTS.items():
        state = flow["states"][tool]
        if state == "idle":
            detail = "Not needed" if finished else "Standing by"
            state = "skipped" if finished else "idle"
        else:
            detail = flow["inputs"].get(tool) or ("Working..." if state == "active" else "Done")
        specialist_nodes.append(node_html(icon, name, state, detail))

    answer_state = "done" if finished else "idle"
    answer_detail = "Answer ready" if finished else "Waiting for the team"

    return (
        '<div class="ad-flow">'
        f'<div class="ad-row">{node_html("💬", "Your request", "done", "Sent to the Main Agent")}</div>'
        '<div class="ad-link on"></div>'
        f'<div class="ad-row">{node_html("🧭", "Main Agent", coordinator_state, coordinator_detail)}</div>'
        f'<div class="ad-link {"on" if any_started else ""}"></div>'
        f'<div class="ad-grid">{"".join(specialist_nodes)}</div>'
        f'<div class="ad-link {"on" if finished else ""}"></div>'
        f'<div class="ad-row">{node_html("✅", "Answer", answer_state, answer_detail)}</div>'
        "</div>"
    )


def routing_summary(flow):
    """One line naming the specialists the Main Agent actually used."""
    used = [AGENTS[tool] for tool, state in flow["states"].items() if state != "idle"]
    specialists = [f"{icon} {name}" for icon, name, _ in used if name != "Memory"]
    parts = [f"Routed to {' · '.join(specialists)}" if specialists else "Answered directly by the Main Agent"]
    if flow["states"]["save_project_fact"] != "idle":
        parts.append("💾 Saved a fact to memory")
    if flow["memory_read"]:
        parts.append(f"Used {flow['memory_read']} saved fact(s)")
    return "  ·  ".join(parts)


@st.dialog(f"About {APP_NAME}", width="large")
def show_about():
    st.markdown(
        f"**{APP_NAME}** is a small, complete multi-agent application built with "
        "**Microsoft AutoGen**. Every agent is an AutoGen `AssistantAgent`. The Main "
        "Agent reads each request and brings in only the "
        "specialists it needs. A simple sum goes to the Calculator Agent alone, while a "
        "feature plan may involve several specialists."
    )
    st.info(
        "The specialists are built for software project questions: planning features, "
        "security, testing and architecture. Other questions are answered by the Main "
        "Agent alone.",
        icon="💡",
    )
    st.markdown("**The agent team**")
    cards = "".join(node_html(icon, name, "", role) for icon, name, role in AGENTS.values())
    st.markdown(
        FLOW_CSS
        + '<div class="ad-about">'
        + node_html("🧭", "Main Agent", "done", "Understands the request, picks specialists and combines their answers")
        + f'<div class="ad-link on"></div><div class="ad-grid">{cards}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**How it works**")
    st.markdown(
        "- Each specialist is an AutoGen `AssistantAgent`, given to the Main Agent as a "
        "**tool**. Choosing a tool is how the Main Agent routes work. *Memory* is a plain "
        "Python tool, not an agent.\n"
        "- While a request runs, the backend streams AutoGen events (`run_stream`), so you "
        "can watch which agents light up.\n"
        "- **Conversation history** lives inside each agent and is cleared by *New chat*.\n"
        "- **ListMemory** keeps lasting project facts the Main Agent decides to save. They "
        "survive *New chat* and are cleared by *New session*.\n"
        "- Every browser tab gets its own session with its own agents and memory."
    )
    st.caption("Built with AutoGen AgentChat · OpenAI gpt-4o-mini · FastAPI · Streamlit")


st.set_page_config(page_title=APP_NAME, page_icon=":material/hub:")
st.markdown(FLOW_CSS, unsafe_allow_html=True)
st.markdown(
    f'<div class="ad-brand">🧭 {APP_NAME}<span>AutoGen multi-agent assistant</span></div>',
    unsafe_allow_html=True,
)
st.caption(
    "A demo of how Microsoft AutoGen agents work together. The Main Agent reads your "
    "request, decides which specialist AutoGen agents to assign, and combines their "
    "answers. Watch the flow light up as each agent works."
)

# st.session_state survives reruns. Each browser tab gets its own.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chats_left" not in st.session_state:
    st.session_state.chats_left = None

session_id = st.session_state.session_id

# Sidebar: reset buttons and the stored ListMemory facts.
with st.sidebar:
    st.markdown(f"### {APP_NAME}")
    st.caption("A multi-agent assistant built with AutoGen")

    if st.button(
        "New chat",
        icon=":material/add:",
        type="primary",
        width="stretch",
    ):
        requests.post(f"{BACKEND_URL}/new-chat", json={"session_id": session_id}, timeout=30)
        st.session_state.messages = []
        st.rerun()
    if st.button(
        "New session",
        icon=":material/restart_alt:",
        width="stretch",
    ):
        requests.post(f"{BACKEND_URL}/new-session", json={"session_id": session_id}, timeout=30)
        st.session_state.messages = []
        st.rerun()
    st.caption("New chat keeps saved facts. New session clears everything.")

    st.divider()
    st.markdown("**Memory**")
    try:
        facts = requests.get(f"{BACKEND_URL}/memory/{session_id}", timeout=30).json()["facts"]
        if not facts:
            st.caption("Facts you share about your project will appear here.")
        for fact in facts:
            st.caption(f"• {fact}")
    except requests.exceptions.ConnectionError:
        st.caption("Memory is unavailable right now.")

    if st.session_state.chats_left is not None:
        st.divider()
        st.caption(f"Demo: {st.session_state.chats_left} chats left")

    st.divider()
    if st.button(f"About {APP_NAME}", icon=":material/info:", type="tertiary"):
        show_about()

# Welcome screen with example prompts, shown only before the first message.
example_prompt = None
if not st.session_state.messages:
    st.markdown("### How can the team help?")
    st.caption(
        "Ask about your software project: features, security, testing or architecture. "
        "The Main Agent brings in only the specialists it needs. Other questions "
        "are answered by the Main Agent alone."
    )
    example_prompt = st.pills("Try an example", EXAMPLE_PROMPTS, label_visibility="collapsed")
    if st.button("See how it works", icon=":material/account_tree:", type="tertiary"):
        show_about()

# Show the conversation so far.
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=AVATARS[message["role"]]):
        st.markdown(message["content"])
        if message.get("flow"):
            st.caption(routing_summary(message["flow"]))
            with st.expander("How this answer was produced"):
                st.markdown(render_flow(message["flow"]), unsafe_allow_html=True)

user_message = st.chat_input(f"Message {APP_NAME}...") or example_prompt

if user_message:
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(user_message)

    # Pass the user's real IP so the backend can apply the demo limit per user.
    headers = {}
    if st.context.ip_address:
        headers["X-Client-IP"] = st.context.ip_address

    flow = {
        "states": {tool: "idle" for tool in AGENTS},
        "inputs": {},
        "memory_read": 0,
        "finished": False,
    }
    answer = None

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        st.caption("Your agent team is working...")
        flow_view = st.empty()
        flow_view.markdown(render_flow(flow), unsafe_allow_html=True)

        try:
            with requests.post(
                f"{BACKEND_URL}/chat",
                json={"session_id": session_id, "message": user_message},
                headers=headers,
                stream=True,
                timeout=300,
            ) as reply:
                if reply.status_code in (400, 429):
                    # Friendly messages from our HTTPException checks.
                    answer = reply.json()["detail"]
                elif reply.status_code == 200:
                    # The backend sends one JSON event per line as the agents work.
                    for line in reply.iter_lines(chunk_size=None):
                        if not line:
                            continue
                        event = json.loads(line)
                        tool = event.get("tool")
                        if event["type"] == "agent_start" and tool in AGENTS:
                            flow["states"][tool] = "active"
                            flow["inputs"][tool] = event["input"]
                        elif event["type"] == "agent_done" and tool in AGENTS:
                            flow["states"][tool] = "done"
                        elif event["type"] == "memory_read":
                            flow["memory_read"] = event["count"]
                        elif event["type"] == "final":
                            flow["finished"] = True
                            answer = event["response"]
                            st.session_state.chats_left = event["chats_left"]
                        flow_view.markdown(render_flow(flow), unsafe_allow_html=True)
        except requests.exceptions.ConnectionError:
            answer = "The service is unavailable right now. Please try again shortly."

    if answer is None:
        answer = "Something went wrong. Please try again."

    st.session_state.messages.append({"role": "user", "content": user_message})
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "flow": flow if flow["finished"] else None,
    })
    # Rerun so the sidebar facts and chats-left counter show the latest values.
    st.rerun()
