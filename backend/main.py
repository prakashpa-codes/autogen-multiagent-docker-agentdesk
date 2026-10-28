import json
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from autogen_core.memory import ListMemory
from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    MemoryQueryEvent,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
)
from autogen_ext.models.openai import OpenAIChatCompletionClient

from backend.agents import create_agents

#load envirionment variables from .env file
load_dotenv()

# Limits come from .env so local and deployed servers can use different values.
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "1000"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1000"))
SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "30"))
# 0 means unlimited (local testing). Set a number for public demos.
DEMO_CHAT_LIMIT = int(os.getenv("DEMO_CHAT_LIMIT", "0"))

# Used by endpoints that only need to know which user is calling.
class SessionRequest(BaseModel):
    session_id: str


# Shape of the JSON the client sends.
class ChatRequest(BaseModel):
    session_id: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts.
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is missing from .env")
    app.state.model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini", max_tokens=MAX_OUTPUT_TOKENS
    )

    # Each session ID maps to its own Main Agent and ListMemory.
    app.state.sessions = {}
    # Number of successful chats per IP address, for the demo limit.
    app.state.chat_counts = {}

    yield
    # Runs once when the server stops.
    await app.state.model_client.close()


app = FastAPI(title="AgentDesk API", lifespan=lifespan)

def remove_idle_sessions():
    """Delete sessions that have not been used for SESSION_IDLE_MINUTES."""
    cutoff = time.time() - SESSION_IDLE_MINUTES * 60
    sessions = app.state.sessions
    for session_id in list(sessions):
        if sessions[session_id]["last_used"] < cutoff:
            del sessions[session_id]


def get_session(session_id: str) -> dict:
    """Return the user's session, creating it on first use."""
    remove_idle_sessions()
    sessions = app.state.sessions
    if session_id not in sessions:
        project_memory = ListMemory()
        sessions[session_id] = {
            "memory": project_memory,
            "main_agent": create_agents(app.state.model_client, project_memory)[0],
        }
    sessions[session_id]["last_used"] = time.time()
    return sessions[session_id]


def to_line(event: dict) -> str:
    """Encode one event as a line of JSON (the NDJSON streaming format)."""
    return json.dumps(event) + "\n"


def tool_input(arguments: str) -> str:
    """Return the task or fact text the Main Agent passed to a tool."""
    try:
        values = json.loads(arguments)
        return str(values.get("task") or values.get("fact") or "")
    except json.JSONDecodeError:
        return ""


@app.post("/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
    x_client_ip: str | None = Header(default=None),
):
    if len(request.message) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Please keep your message under {MAX_INPUT_CHARS} characters.",
        )

    # Streamlit sends the user's real IP. Otherwise use the direct caller's IP.
    client_ip = x_client_ip or http_request.client.host
    chats_used = app.state.chat_counts.get(client_ip, 0)

    if DEMO_CHAT_LIMIT > 0 and chats_used >= DEMO_CHAT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used all {DEMO_CHAT_LIMIT} demo chats. "
                "Thanks for trying the assistant!"
            ),
        )

    session = get_session(request.session_id)

    async def event_stream():
        # run_stream() yields each step as it happens, then the final TaskResult.
        # Tool calls are how the Main Agent delegates, so they show which
        # specialists are working.
        memory_items_used = 0
        try:
            async for item in session["main_agent"].run_stream(task=request.message):
                if isinstance(item, MemoryQueryEvent):
                    memory_items_used += len(item.content)
                    yield to_line({"type": "memory_read", "count": len(item.content)})
                elif isinstance(item, ToolCallRequestEvent):
                    for call in item.content:
                        yield to_line({
                            "type": "agent_start",
                            "tool": call.name,
                            "input": tool_input(call.arguments),
                        })
                elif isinstance(item, ToolCallExecutionEvent):
                    for call_result in item.content:
                        yield to_line({"type": "agent_done", "tool": call_result.name})
                elif isinstance(item, TaskResult):
                    # Count the chat only after it succeeds.
                    chats_used = app.state.chat_counts.get(client_ip, 0) + 1
                    app.state.chat_counts[client_ip] = chats_used
                    chats_left = DEMO_CHAT_LIMIT - chats_used if DEMO_CHAT_LIMIT > 0 else None
                    yield to_line({
                        "type": "final",
                        "response": str(item.messages[-1].content),
                        "memory_items_used": memory_items_used,
                        "chats_left": chats_left,
                    })
        except Exception as error:
            print(f"[Error] {error}")
            yield to_line({"type": "error"})

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@app.post("/new-chat")
async def new_chat(request: SessionRequest):
    # Fresh agents have empty histories. The session's ListMemory is kept.
    session = get_session(request.session_id)
    session["main_agent"] = create_agents(app.state.model_client, session["memory"])[0]
    return {"message": "New chat started. Agent histories cleared. Stored memory kept."}


@app.post("/new-session")
async def new_session(request: SessionRequest):
    # Removing the session drops its agents and ListMemory.
    app.state.sessions.pop(request.session_id, None)
    return {"message": "New session started. Agent histories and stored memory cleared."}


@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    # Reading memory should not create a session, so check first.
    session = app.state.sessions.get(session_id)
    if session is None:
        return {"facts": []}
    stored = await session["memory"].query("")
    return {"facts": [str(item.content) for item in stored.results]}

