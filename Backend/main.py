    return {
        "status": "ok",
        "service": "Bunny AI",
        "backend": "online",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "personal_api_keys_supported": True,
        "api_fallback": "render_environment_key",
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "standard_output_tokens": _safe_int_env("GEMINI_MAX_OUTPUT_TOKENS", 8192),
        "code_output_tokens": _safe_int_env("GEMINI_CODE_MAX_OUTPUT_TOKENS", 16384),
    }


# ---------------------------------------------------------------------------
# Chat route
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    # A personal key takes precedence for this request only. Otherwise use the
    # existing Render environment key so users can chat without adding a key.
    api_key = (payload.api_key or "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini API is not configured. Add GEMINI_API_KEY to the Render "
                "backend environment, or enter your own Gemini API key in Bunny Settings."
            ),
        )
    session_id = get_session_id(payload.session_id)
    bunny, session_lock = get_session_resources(session_id)

    try:
        # Bunny's conversation history is stateful. Serialize requests per session.
        result = await run_in_threadpool(
            _run_bunny_message,
            bunny,
            session_lock,
            message,
            api_key,
        )
    except HTTPException:
        raise
    except Exception as exc:  # Keep internal details in server logs only.
        # Do not log the request payload or API key. ai.py redacts the key from
        # Gemini exception text before raising, and the response stays generic.
        logger.exception("Bunny failed to process a message for session %s", session_id)
        raise HTTPException(
            status_code=500,
            detail="Bunny could not process this request. Check the backend logs.",
        ) from exc

    reply = str(result.get("reply") or "Bunny could not generate a response.")
    action = result.get("action")
    if not isinstance(action, dict):
        action = None

    return ChatResponse(reply=reply, action=action, session_id=session_id)


def _run_bunny_message(
    bunny: Bunny,
    session_lock: threading.RLock,
    message: str,
    api_key: str,
) -> dict[str, Any]:
    with session_lock:
        return bunny.handle_message(message, api_key)


# ---------------------------------------------------------------------------
# Session and memory routes
# ---------------------------------------------------------------------------
@app.post("/api/session/clear")
def clear_session(payload: SessionRequest) -> dict[str, Any]:
    session_id = get_session_id(payload.session_id)
    clear_history(session_id)
    clear_memory(session_id)
    with _SESSION_MAP_LOCK:
        _ACTIVE_BUNNIES.pop(session_id, None)
        _SESSION_LOCKS.pop(session_id, None)
    return {
        "ok": True,
        "session_id": session_id,
        "message": "Session cleared successfully.",
    }


@app.delete("/api/session")
def delete_session_endpoint(payload: SessionRequest) -> dict[str, Any]:
    session_id = get_session_id(payload.session_id)
    delete_session(session_id)
    with _SESSION_MAP_LOCK:
        _ACTIVE_BUNNIES.pop(session_id, None)
        _SESSION_LOCKS.pop(session_id, None)
    return {
        "ok": True,
        "session_id": session_id,
        "message": "Session deleted successfully.",
    }


@app.get("/api/session/{session_id}/memory")
def get_session_memory(session_id: str) -> dict[str, str]:
    safe_session_id = get_session_id(session_id)
    return {
        "session_id": safe_session_id,
        "memory": load_memory(safe_session_id),
    }


# ---------------------------------------------------------------------------
# Local development entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
