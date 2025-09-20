# pip install "langchain>=0.2" pydantic requests

import time
import json
import re
import requests
from typing import List, Iterable, Optional, Dict, Any
from pydantic import Field, BaseModel
from requests.auth import HTTPBasicAuth

from langchain_core.messages import BaseMessage, AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.runnables import RunnableConfig

class MicronAuthConfig(BaseModel):
    token_url: str = Field(..., description="OAuth token endpoint (client credentials)")
    client_key: str = Field(..., description="Client key / id")
    client_secret: str = Field(..., description="Client secret")
    subscription_key: str = Field(..., description="Micron API subscriptionKey header")
    # token cache
    access_token: Optional[str] = None
    token_acquired_at: Optional[float] = None
    expires_in: int = 3000  # 如果 token 回應沒有 expires_in，可用預設值

class MicronChatModel(SimpleChatModel):
    """
    A LangChain ChatModel wrapper for Micron LLM Service.
    Implements both sync (_call) and streaming (_stream).

    Notes:
    - Uses OAuth Client Credentials to acquire access_token from token_url.
    - Calls generate_url with required headers including `subscriptionKey`.
    - If the backend later supports native streaming, you can flip `use_native_stream=True`.
    """

    # ---- Micron endpoints / auth ----
    token_url: str = Field(...)
    generate_url: str = Field(...)
    client_key: str = Field(...)
    client_secret: str = Field(...)
    subscription_key: str = Field(...)

    # ---- Inference defaults ----
    model: str = "gpt-4.1"
    temperature: float = 0.2
    top_p: float = 0.8
    max_tokens: int = 2000
    stop_words: Optional[List[str]] = None  # default handled in _build_payload

    # ---- Behavior ----
    timeout: int = 60
    retries: int = 2
    use_native_stream: bool = False  # set True if backend supports SSE/chunked
    simulate_stream_chunk: str = "token"  # "token" | "sentence" | "line"
    simulate_stream_sleep: float = 0.0     # small delay between chunks for UX (e.g., 0.01~0.03)

    # ---- Internal token cache ----
    _access_token: Optional[str] = None

    # ----------------- Public LangChain methods -----------------

    def _call(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> AIMessage:
        """Synchronous call -> returns one AIMessage."""
        self._ensure_access_token()
        payload = self._build_payload(messages, stop, **kwargs)
        headers = self._build_headers()

        # Retry a bit on transient errors (401 to refresh token; 5xx to retry)
        for attempt in range(self.retries + 1):
            resp = requests.post(self.generate_url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 401 and attempt < self.retries:
                # token may be expired -> refresh once and retry
                self._refresh_token()
                headers = self._build_headers()
                continue
            if 500 <= resp.status_code < 600 and attempt < self.retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            text = self._extract_text(data)
            return AIMessage(content=text)

        # if loop exits abnormally
        raise RuntimeError("MicronChatModel: request failed after retries")

    def _stream(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> Iterable[AIMessageChunk]:
        """Streaming call -> yields AIMessageChunk pieces."""
        if self.use_native_stream:
            # TODO: implement when Micron API offers SSE/chunked responses.
            # For now, we fall back to sync + simulate streaming.
            pass

        # Fallback: call sync once, then chunk on client side.
        result_msg = self._call(messages, stop=stop, **kwargs)
        content = result_msg.content

        for piece in self._chunk_text(content, mode=self.simulate_stream_chunk):
            if self.simulate_stream_sleep:
                time.sleep(self.simulate_stream_sleep)
            yield AIMessageChunk(content=piece)

    # ----------------- Helpers -----------------

    def _ensure_access_token(self):
        """Acquire token if missing; lazy init."""
        if not self._access_token:
            self._refresh_token()

    def _refresh_token(self):
        """Client Credentials flow to fetch access_token."""
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"grant_type": "client_credentials"}
        auth = HTTPBasicAuth(self.client_key, self.client_secret)
        resp = requests.post(self.token_url, headers=headers, data=data, auth=auth, timeout=self.timeout)
        resp.raise_for_status()
        tok = resp.json()
        # expected: {"access_token": "...", "expires_in": 3600, ...}
        self._access_token = tok.get("access_token")
        if not self._access_token:
            raise RuntimeError("No access_token in token response")
        # optional: store expiry if present
        # self._token_expiry_ts = time.time() + tok.get("expires_in", 3000)

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            # IMPORTANT: Micron requires 'subscriptionKey' (per your code)
            "subscriptionKey": self.subscription_key,
        }

    def _extract_text(self, data: Dict[str, Any]) -> str:
        """
        Your current helper returns response.json() directly.
        If the service returns {"text": "..."} or {"output": "..."} adjust here.
        For now, try a few common keys and finally stringify.
        """
        for k in ("output", "text", "result", "data", "message", "content"):
            if isinstance(data, dict) and k in data and isinstance(data[k], str):
                return data[k]
        # If backend returns nested structure, map it here once you know the shape.
        return json.dumps(data, ensure_ascii=False)

    def _build_payload(self, messages: List[BaseMessage], stop: Optional[List[str]], **kwargs) -> Dict[str, Any]:
        """
        Map LangChain messages -> Micron payload schema:
        { sys_prompt, prompt, model, temperature, top_p, max_tokens, stop_words }
        """
        # 1) Merge system messages
        sys_prompts = [m.content for m in messages if isinstance(m, SystemMessage)]
        sys_prompt = "\n".join(sys_prompts).strip() if sys_prompts else ""

        # 2) Flatten the rest into a single "prompt" preserving roles
        convo_lines = []
        for m in messages:
            if isinstance(m, SystemMessage):
                continue
            role = "User" if isinstance(m, HumanMessage) else "AI"
            convo_lines.append(f"{role}: {m.content}")
        prompt_text = "\n".join(convo_lines).strip()

        # 3) Assemble payload with defaults + user overrides
        payload = {
            "sys_prompt": sys_prompt,
            "prompt": prompt_text,
            "model": kwargs.get("model", self.model),
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stop_words": kwargs.get("stop_words", stop or self.stop_words or ["User:", "AI:"]),
        }
        return payload

    def _chunk_text(self, text: str, mode: str = "token") -> Iterable[str]:
        """Client-side chunking for simulated streaming."""
        if not text:
            return []
        if mode == "sentence":
            # split by Chinese/Japanese full stop or period/question/exclamation
            parts = re.split(r'(?<=[。！？!?])\s*', text)
            for p in parts:
                if p:
                    yield p
        elif mode == "line":
            for line in text.splitlines(True):
                if line:
                    yield line
        else:
            # token-ish: split on whitespace and punctuation into small chunks
            # keep chunks short (~8-12 chars) for smoother UX
            buf = ""
            for ch in text:
                buf += ch
                if len(buf) >= 12 or ch in " \n，。.,!?！？；;":
                    yield buf
                    buf = ""
            if buf:
                yield buf
