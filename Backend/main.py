"""
Bunny AI - FastAPI backend.

The browser sends only:
    message
    session_id

The Gemini API key is stored server-side as:
    GEMINI_API_KEY

It is never returned to the frontend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import (
    FastAPI,
    HTTPException,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai import (
    generate_reply,
    is_configured,
)


# =========================================================
# App
# =========================================================

app = FastAPI(
    title="Bunny AI Backend",
    description="Secure server-side Gemini backend for Bunny AI.",
    version="2.0.0",
)


# =========================================================
# CORS
# =========================================================

ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "http://localhost:5500",

    # GitHub Pages
    "https://anup-prasad008.github.io",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
        "Accept",
    ],
)


# =========================================================
# In-memory sessions
# =========================================================

sessions: Dict[
    str,
    List[Dict[str, str]]
] = {}


session_created_at: Dict[
    str,
    str
] = {}


# =========================================================
# Request models
# =========================================================

class ChatRequest(BaseModel):
    """
    Request received from the frontend.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000
    )

    session_id: Optional[str] = Field(
        default=None,
        max_length=200
    )


class SessionRequest(BaseModel):
    """
    Request used for session operations.
    """

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=200
    )


# =========================================================
# Helpers
# =========================================================

def ensure_session(
    session_id: Optional[str]
) -> str:
    """
    Create a new session if needed.
    """

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required."
        )

    if session_id not in sessions:
        sessions[session_id] = []

        session_created_at[
            session_id
        ] = datetime.now(
            timezone.utc
        ).isoformat()

    return session_id


def get_session_history(
    session_id: str
) -> List[Dict[str, str]]:
    """
    Return a copy of session history.
    """

    return list(
        sessions.get(
            session_id,
            []
        )
    )


def add_history_message(
    session_id: str,
    role: str,
    content: str
) -> None:
    """
    Add one message to session history.
    """

    if session_id not in sessions:
        sessions[session_id] = []

    sessions[
        session_id
    ].append(
        {
            "role": role,
            "content": content,
        }
    )

    # Keep memory under control.
    # Last 40 messages = roughly 20 turns.
    sessions[
        session_id
    ] = sessions[
        session_id
    ][-40:]


def make_action(
    message: str
) -> Optional[dict]:
    """
    Handle simple browser-open commands.

    This is intentionally kept separate from Gemini.
    """

    lowered = message.strip().lower()

    website_map = {
        "youtube": "https://www.youtube.com/",
        "open youtube": "https://www.youtube.com/",

        "google": "https://www.google.com/",
        "open google": "https://www.google.com/",

        "github": "https://github.com/",
        "open github": "https://github.com/",

        "linkedin": "https://www.linkedin.com/",
        "open linkedin": "https://www.linkedin.com/",
    }

    if lowered in website_map:
        return {
            "type": "open_url",
            "url": website_map[lowered],
        }

    return None


# =========================================================
# Root
# =========================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Bunny AI Backend",
        "version": "2.0.0",
        "gemini_configured": is_configured(),
    }


# =========================================================
# Health
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "gemini_configured": is_configured(),
    }


# =========================================================
# Chat
# =========================================================

@app.post("/api/chat")
def chat(request: ChatRequest):
    """
    Main Bunny AI endpoint.

    IMPORTANT:
    No API key is accepted from the browser.
    """

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    session_id = (
        request.session_id
        or f"session-{datetime.now(timezone.utc).timestamp()}"
    )

    ensure_session(
        session_id
    )

    # -----------------------------------------------------
    # Browser action
    # -----------------------------------------------------

    action = make_action(
        message
    )

    if action:
        reply = (
            "Sure — opening it for you."
        )

        add_history_message(
            session_id,
            "user",
            message
        )

        add_history_message(
            session_id,
            "assistant",
            reply
        )

        return {
            "success": True,
            "reply": reply,
            "session_id": session_id,
            "action": action,
        }

    # -----------------------------------------------------
    # Gemini
    # -----------------------------------------------------

    if not is_configured():
        raise HTTPException(
            status_code=500,
            detail=(
                "Server API key is not configured. "
                "Please set GEMINI_API_KEY in the backend environment."
            )
        )

    history = get_session_history(
        session_id
    )

    try:
        reply = generate_reply(
            user_message=message,
            history=history
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc)
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected backend error: {exc}"
        ) from exc

    # -----------------------------------------------------
    # Save conversation
    # -----------------------------------------------------

    add_history_message(
        session_id,
        "user",
        message
    )

    add_history_message(
        session_id,
        "assistant",
        reply
    )

    return {
        "success": True,
        "reply": reply,
        "session_id": session_id,
        "action": None,
    }


# =========================================================
# Clear session
# =========================================================

@app.post("/api/session/clear")
def clear_session(
    request: SessionRequest
):
    """
    Clear conversation messages but keep the session ID.
    """

    session_id = request.session_id

    ensure_session(
        session_id
    )

    sessions[
        session_id
    ] = []

    return {
        "success": True,
        "session_id": session_id,
        "message": "Conversation cleared.",
    }


# =========================================================
# Delete session
# =========================================================

@app.delete("/api/session")
def delete_session(
    request: SessionRequest
):
    """
    Completely remove a session.
    """

    session_id = request.session_id

    sessions.pop(
        session_id,
        None
    )

    session_created_at.pop(
        session_id,
        None
    )

    return {
        "success": True,
        "session_id": session_id,
        "message": "Session deleted.",
    }


# =========================================================
# Session memory
# =========================================================

@app.get(
    "/api/session/{session_id}/memory"
)
def get_memory(
    session_id: str
):
    """
    Return a simple session-memory summary.

    This uses stored conversation history and does not
    expose any API credential.
    """

    if session_id not in sessions:
        return {
            "session_id": session_id,
            "memory": "No saved memory yet.",
            "messages": 0,
        }

    history = sessions[
        session_id
    ]

    user_messages = [
        item["content"]
        for item in history
        if item["role"] == "user"
    ]

    if not user_messages:
        memory_text = (
            "No saved memory yet."
        )
    else:
        recent = user_messages[-10:]

        memory_lines = [
            "Recent conversation topics:"
        ]

        for index, item in enumerate(
            recent,
            start=1
        ):
            memory_lines.append(
                f"{index}. {item}"
            )

        memory_text = "\n".join(
            memory_lines
        )

    return {
        "session_id": session_id,
        "memory": memory_text,
        "messages": len(history),
    }


# =========================================================
# Render / local server
# =========================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
