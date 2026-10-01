"""
Bunny AI - Gemini service layer.

The Gemini API key is intentionally loaded from the
GEMINI_API_KEY environment variable.

The frontend never receives or sends this API key.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from google import genai


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


# ---------------------------------------------------------
# Gemini client
# ---------------------------------------------------------

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """
    Return a shared Gemini client.

    The API key comes only from the server environment.
    """

    global _client

    if _client is not None:
        return _client

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not configured."
        )

    _client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    return _client


# ---------------------------------------------------------
# Bunny personality
# ---------------------------------------------------------

SYSTEM_INSTRUCTION = """
You are Bunny, a friendly AI assistant.

Your job is to help users clearly, accurately and politely.

Personality:
- Friendly
- Helpful
- Calm
- Natural
- Concise when possible
- Detailed when necessary

Instructions:
1. Answer the user's question directly.
2. Do not mention internal API keys, server variables or implementation details.
3. Do not ask for a Gemini API key.
4. Do not tell users to configure an API key in the browser.
5. Use Markdown when it makes the answer easier to read.
6. For code, provide clean and properly formatted code.
7. If the user asks a calculation, calculate it carefully.
8. If information is uncertain, clearly say so.
"""


# ---------------------------------------------------------
# Session conversation formatting
# ---------------------------------------------------------

def build_prompt(
    history: List[Dict[str, str]],
    user_message: str
) -> str:
    """
    Convert session history into a Gemini prompt.
    """

    parts: List[str] = [
        SYSTEM_INSTRUCTION.strip()
    ]

    if history:
        parts.append(
            "\nConversation history:"
        )

        for item in history:
            role = item.get(
                "role",
                "user"
            )

            content = item.get(
                "content",
                ""
            )

            if not content:
                continue

            if role == "assistant":
                label = "Bunny"
            else:
                label = "User"

            parts.append(
                f"{label}: {content}"
            )

    parts.append(
        f"\nUser: {user_message}"
    )

    parts.append(
        "\nBunny:"
    )

    return "\n\n".join(parts)


# ---------------------------------------------------------
# Gemini request
# ---------------------------------------------------------

def generate_reply(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Send a message to Gemini and return the generated text.
    """

    if not user_message.strip():
        raise ValueError(
            "Message cannot be empty."
        )

    history = history or []

    client = get_client()

    prompt = build_prompt(
        history=history,
        user_message=user_message
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gemini API request failed: {exc}"
        ) from exc

    text = getattr(
        response,
        "text",
        None
    )

    if not text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return text.strip()


# ---------------------------------------------------------
# Health helper
# ---------------------------------------------------------

def is_configured() -> bool:
    """
    Check whether the Gemini API key exists.

    This does not expose the actual key.
    """

    return bool(
        GEMINI_API_KEY
    )
