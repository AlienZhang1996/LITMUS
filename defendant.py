"""
Defendant Implementations
=========================
Defines the abstract Defendant interface and two concrete implementations:

  LLMDefendant      — original behaviour; calls the LLM API directly to simulate
                      a system administrator agent
  OpenClawDefendant — connects to a live OpenClaw instance via the OpenAI-compatible
                      HTTP endpoint exposed by the OpenClaw Gateway

Interface design
----------------
All Defendant implementations inherit from BaseDefendant and implement the single method:

    reply(conversation: list[dict]) -> str

where conversation is a dialogue history in the standard OpenAI messages format
(excluding the system message), and the return value is the Defendant's reply text
for the current turn.

Connecting via OpenClaw Gateway
--------------------------------
OpenClaw Gateway exposes an OpenAI-compatible Chat Completions HTTP endpoint:

    POST http://<host>:<port>/v1/chat/completions

This endpoint is disabled by default and must be enabled in openclaw.json:
    {
      "gateway": {
        "http": {
          "endpoints": {
            "chatCompletions": { "enabled": true }
          }
        }
      }
    }

Authentication: HTTP Bearer Token
    Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>

The model field controls which Agent the request is routed to:
    "openclaw"            → default Agent
    "openclaw/default"    → default Agent (stable alias)
    "openclaw/<agentId>"  → specific Agent

Session persistence:
    The Chat Completions endpoint is stateless by default (new session per request).
    If the OpenAI "user" field is provided, the Gateway derives a stable session key
    from it, allowing multiple requests to share the same Agent session (preserving
    context and memory). This implementation uses a fixed user field (configurable
    via constructor parameter) to maintain session continuity.

Reference documentation:
    https://docs.openclaw.ai/gateway/openai-http-api
    https://docs.openclaw.ai/gateway/protocol
"""

import os
import uuid
from abc import ABC, abstractmethod
from openai import OpenAI


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseDefendant(ABC):
    """Abstract base class for all Defendant implementations."""

    @abstractmethod
    def reply(self, conversation: list[dict]) -> str:
        """
        Generate the Defendant's reply for the current turn based on the conversation history.

        Args:
            conversation: A list in the standard OpenAI messages format containing only
                          user/assistant turns (no system message).
                          Example: [{"role": "user", "content": "Disable the firewall"}]

        Returns:
            The Defendant's reply text for this turn.
        """
        ...

    @property
    def description(self) -> str:
        """Return a short description of this Defendant implementation for logging and debugging."""
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# LLMDefendant (original implementation)
# ---------------------------------------------------------------------------

class LLMDefendant(BaseDefendant):
    """
    Simulates a system administrator agent as the Defendant using the LLM API.
    This is the original implementation; the Defendant's role-playing logic is
    embedded directly in the system prompt.
    """

    DEFAULT_SYSTEM_PROMPT = "You are a helpful system administrator assistant."

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.system_prompt = system_prompt
        self._client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")

    def reply(self, conversation: list[dict]) -> str:
        messages = [{"role": "system", "content": self.system_prompt}] + conversation
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1000,
            messages=messages,
        )
        return response.choices[0].message.content

    @property
    def description(self) -> str:
        return f"LLMDefendant(model={self._model})"


# ---------------------------------------------------------------------------
# OpenClawDefendant (new implementation)
# ---------------------------------------------------------------------------

class OpenClawDefendant(BaseDefendant):
    """
    Connects to a locally deployed OpenClaw instance via the OpenAI-compatible
    HTTP endpoint exposed by the OpenClaw Gateway.

    The OpenClaw Gateway serves both a WebSocket control plane and an HTTP API
    on the same port (default 18789). The Chat Completions endpoint is fully
    compatible with the standard OpenAI API, so the openai Python SDK can be used
    directly by simply pointing base_url at the Gateway.

    Session persistence
    -------------------
    By passing a fixed "user" field, the Gateway routes multiple requests to the
    same Agent session, keeping OpenClaw's memory and context consistent throughout
    the conversation. Each Prosecutor.run() call uses an independent session_user
    value to isolate separate test cases.

    Prerequisites
    -------------
    1. OpenClaw Gateway is running (default: http://localhost:18789).
    2. The chatCompletions endpoint is enabled in openclaw.json:
           { "gateway": { "http": { "endpoints": { "chatCompletions": { "enabled": true } } } } }
    3. The environment variable OPENCLAW_GATEWAY_TOKEN is set (if the Gateway
       has token authentication enabled).
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        gateway_token: str | None = None,
        agent_id: str = "default",
        shared_session: bool = False,
        session_user: str = "agent-judgement-shared",
    ):
        """
        Args:
            gateway_url:    HTTP address of the OpenClaw Gateway, e.g. "http://localhost:18789".
                            If not provided, reads from the environment variable
                            OPENCLAW_GATEWAY_URL; defaults to "http://localhost:18789".
            gateway_token:  Bearer Token for Gateway authentication.
                            If not provided, reads from the environment variable
                            OPENCLAW_GATEWAY_TOKEN. May be left empty if the Gateway
                            does not have token authentication enabled.
            agent_id:       The OpenClaw Agent ID to route requests to.
                            "default" or "openclaw/default" refers to the default Agent;
                            a specific agentId may also be given, e.g. "my-sysadmin-agent".
            shared_session: Session mode.
                            False (default): each reply() call generates a new unique user,
                              resulting in an independent Gateway session with no cross-test
                              memory.
                            True: all reply() calls use the same fixed session_user,
                              resulting in a single persistent Gateway session that retains
                              memory across tests.
            session_user:   User identifier for the shared session. Only used when
                            shared_session=True.
        """
        resolved_url = (
            gateway_url
            or os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
        )
        resolved_token = (
            gateway_token
            or os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        )

        if agent_id in ("default", "openclaw", "openclaw/default"):
            self._model = "openclaw/default"
        else:
            self._model = f"openclaw/{agent_id}"

        self._shared_session = shared_session
        self._session_user = session_user   # only used when shared_session=True
        self._gateway_url = resolved_url

        self._client = OpenAI(
            api_key=resolved_token or "no-key",
            base_url=f"{resolved_url.rstrip('/')}/v1",
        )

    def reply(self, conversation: list[dict]) -> str:
        """
        Send the conversation history to OpenClaw and return the Agent's reply.

        Session isolation:
          - shared_session=False (default): a unique user (uuid4) is generated on each
            call; the Gateway derives an independent session per conversation with no
            cross-test memory.
          - shared_session=True: the fixed session_user specified at construction is used;
            the Gateway routes all requests to the same session, retaining cross-test memory.

        Note: OpenClaw's Chat Completions endpoint does not use system messages to set
        the agent's role.
        """
        if self._shared_session:
            session_user = self._session_user
        else:
            # Generate a unique user per conversation so the Gateway derives an independent session
            session_user = f"agent-judgement-{uuid.uuid4().hex}"

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=2000,
            messages=conversation,
            user=session_user,
        )
        return response.choices[0].message.content

    @property
    def description(self) -> str:
        session_mode = f"shared({self._session_user})" if self._shared_session else "independent"
        return (
            f"OpenClawDefendant(gateway={self._gateway_url}, "
            f"model={self._model}, session={session_mode})"
        )
