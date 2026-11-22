"""
Ollama client adapter for Reckon notebooks.

Provides a minimal client for interacting with local Ollama instances.
Designed for notebook use with graceful degradation when Ollama is unavailable.

Requirements:
    - Ollama running locally: https://ollama.ai/
    - No Python package dependencies (uses stdlib only)
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from typing import Any, Optional, Generator
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

__all__ = [
    "OllamaConfig",
    "ollama_healthcheck",
    "ollama_list_models",
    "ollama_chat",
    "ollama_chat_stream",
    "ollama_chat_json",
    "parse_agent_response",
    "OLLAMA_AVAILABLE",
    "get_install_command",
]

# Default base URL for local Ollama
DEFAULT_BASE_URL = "http://localhost:11434"

# Default options for deterministic-ish outputs
DEFAULT_OPTIONS = {
    "temperature": 0.1,  # Low temperature for more deterministic outputs
    "top_p": 0.9,
    "top_k": 40,
    # Note: seed is not universally supported by all Ollama models
    # Some models ignore it entirely
}


@dataclass
class OllamaConfig:
    """Configuration for Ollama client."""
    base_url: str = DEFAULT_BASE_URL
    default_model: str = "llama3.2"
    timeout_s: int = 60
    options: dict = field(default_factory=lambda: DEFAULT_OPTIONS.copy())

    def __post_init__(self) -> None:
        # Ensure no trailing slash
        self.base_url = self.base_url.rstrip("/")


def get_install_command() -> str:
    """Get installation instructions for Ollama."""
    return (
        "# Install Ollama:\n"
        "# macOS/Linux: curl -fsSL https://ollama.ai/install.sh | sh\n"
        "# Then pull a model: ollama pull llama3.2\n"
        "# Start server: ollama serve"
    )


def _make_request(
    url: str,
    data: Optional[dict] = None,
    timeout_s: int = 10,
    method: str = "GET",
) -> dict:
    """
    Make an HTTP request to Ollama API.

    Args:
        url: Full URL to request
        data: JSON body for POST requests
        timeout_s: Request timeout in seconds
        method: HTTP method

    Returns:
        Parsed JSON response

    Raises:
        URLError: If connection fails
        HTTPError: If server returns error status
        json.JSONDecodeError: If response is not valid JSON
    """
    headers = {"Content-Type": "application/json"}

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")
    else:
        req = Request(url, headers=headers, method=method)

    with urlopen(req, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_healthcheck(base_url: str = DEFAULT_BASE_URL, timeout_s: int = 5) -> bool:
    """
    Check if Ollama server is reachable and responding.

    Args:
        base_url: Ollama API base URL
        timeout_s: Connection timeout in seconds

    Returns:
        True if Ollama is healthy, False otherwise
    """
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        _make_request(url, timeout_s=timeout_s)
        return True
    except (URLError, HTTPError, socket.timeout, OSError, json.JSONDecodeError):
        return False


def ollama_list_models(base_url: str = DEFAULT_BASE_URL, timeout_s: int = 10) -> list[str]:
    """
    List available models from Ollama.

    Args:
        base_url: Ollama API base URL
        timeout_s: Request timeout in seconds

    Returns:
        List of model names (e.g., ["llama3.2", "codellama"])
        Empty list if Ollama is unavailable
    """
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        response = _make_request(url, timeout_s=timeout_s)
        models = response.get("models", [])
        return [m.get("name", "") for m in models if m.get("name")]
    except (URLError, HTTPError, socket.timeout, OSError, json.JSONDecodeError):
        return []


def ollama_chat(
    model: str,
    messages: list[dict[str, str]],
    base_url: str = DEFAULT_BASE_URL,
    options: Optional[dict] = None,
    timeout_s: int = 120,
    stream: bool = False,
    format: Optional[str] = None,
) -> dict[str, Any]:
    """
    Send a chat request to Ollama.

    Uses the /api/chat endpoint following the official Ollama API schema.

    Args:
        model: Model name (e.g., "llama3.2")
        messages: List of message dicts with "role" and "content" keys
                 Roles: "system", "user", "assistant"
        base_url: Ollama API base URL
        options: Model options (temperature, top_p, etc.)
                 If None, uses DEFAULT_OPTIONS
        timeout_s: Request timeout in seconds
        stream: If True, return streaming response (not yet implemented)
        format: Output format - "json" enables JSON mode for structured outputs

    Returns:
        Response dict with structure:
        {
            "model": "llama3.2",
            "created_at": "...",
            "message": {
                "role": "assistant",
                "content": "..."
            },
            "done": true,
            "total_duration": ...,
            "prompt_eval_count": ...,
            "eval_count": ...
        }

    Raises:
        URLError: If connection fails
        HTTPError: If request fails (e.g., model not found)

    Example:
        response = ollama_chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"},
            ]
        )
        print(response["message"]["content"])
    """
    if stream:
        raise NotImplementedError(
            "Streaming not implemented. Use ollama_chat_stream() for streaming."
        )

    url = f"{base_url.rstrip('/')}/api/chat"

    # Merge default options with provided options
    final_options = DEFAULT_OPTIONS.copy()
    if options:
        final_options.update(options)

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": final_options,
    }

    # Enable JSON mode if requested (Ollama structured output)
    if format is not None:
        payload["format"] = format

    return _make_request(url, data=payload, timeout_s=timeout_s)


def ollama_chat_stream(
    model: str,
    messages: list[dict[str, str]],
    base_url: str = DEFAULT_BASE_URL,
    options: Optional[dict] = None,
    timeout_s: int = 120,
) -> Generator[dict[str, Any], None, None]:
    """
    Send a streaming chat request to Ollama.

    Yields partial response chunks as they arrive.

    Args:
        model: Model name
        messages: List of message dicts
        base_url: Ollama API base URL
        options: Model options
        timeout_s: Request timeout

    Yields:
        Partial response dicts containing "message.content" fragments

    Example:
        for chunk in ollama_chat_stream("llama3.2", messages):
            if "message" in chunk:
                print(chunk["message"]["content"], end="", flush=True)
    """
    url = f"{base_url.rstrip('/')}/api/chat"

    final_options = DEFAULT_OPTIONS.copy()
    if options:
        final_options.update(options)

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": final_options,
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = Request(url, data=body, headers=headers, method="POST")

    with urlopen(req, timeout=timeout_s) as response:
        for line in response:
            if line.strip():
                try:
                    chunk = json.loads(line.decode("utf-8"))
                    yield chunk
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue


# === Agent Protocol ===

AGENT_SYSTEM_PROMPT = """You are an assistant with access to external memory and tools.

IMPORTANT: You MUST respond with valid JSON only. No other text.

Response format (strict JSON):
{
  "tool": {"name": "tool_name", "args": {"arg1": "value1"}} | null,
  "final": "Your message to the user (required)",
  "memory_write": [{"tag": "category", "content": "what to remember"}] | []
}

Available tools:
- calculator: {"expr": "math expression"} -> numeric result
- local_search: {"query": "search terms"} -> text snippets
- scratchpad_write: {"key": "name", "value": "data"} -> stored
- scratchpad_read: {"key": "name"} -> stored value
- schema_validate: {"json_str": "JSON string"} -> validation result

Rules:
1. If a tool is needed, set "tool" with name and args
2. Always provide a "final" message
3. Use "memory_write" to remember important facts
4. Respond ONLY with JSON, no markdown or explanation"""


def parse_agent_response(response_text: str) -> dict[str, Any]:
    """
    Parse agent response into structured format.

    Expects strict JSON matching the agent protocol:
    {
        "tool": {"name": "...", "args": {...}} | null,
        "final": "message to user",
        "memory_write": [{"tag": "...", "content": "..."}] | []
    }

    Args:
        response_text: Raw response from LLM

    Returns:
        Parsed response dict with validated structure

    Raises:
        ValueError: If JSON is invalid or missing required fields

    Note:
        No regex hacks - requires strict JSON. Invalid responses
        should be treated as failure steps and logged.
    """
    # Strip any leading/trailing whitespace
    text = response_text.strip()

    # Handle common markdown wrapping (```json ... ```)
    # But we still require the content to be valid JSON
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines if they're code fences
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Parse JSON
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}") from e

    # Validate structure
    if not isinstance(parsed, dict):
        raise ValueError(f"Response must be a JSON object, got {type(parsed).__name__}")

    # Validate required fields
    if "final" not in parsed:
        raise ValueError("Response missing required 'final' field")

    if not isinstance(parsed.get("final"), str):
        raise ValueError("'final' field must be a string")

    # Validate tool field if present
    tool = parsed.get("tool")
    if tool is not None:
        if not isinstance(tool, dict):
            raise ValueError("'tool' field must be an object or null")
        if "name" not in tool:
            raise ValueError("'tool' object missing 'name' field")
        if "args" not in tool:
            raise ValueError("'tool' object missing 'args' field")

    # Validate memory_write if present
    memory_write = parsed.get("memory_write", [])
    if not isinstance(memory_write, list):
        raise ValueError("'memory_write' must be an array")

    for i, item in enumerate(memory_write):
        if not isinstance(item, dict):
            raise ValueError(f"memory_write[{i}] must be an object")
        if "tag" not in item or "content" not in item:
            raise ValueError(f"memory_write[{i}] missing 'tag' or 'content'")

    # Return normalized structure
    return {
        "tool": tool,
        "final": parsed["final"],
        "memory_write": memory_write,
    }


def _log_json_parse_failure(content: str, error: Exception, is_retry: bool = False) -> None:
    """
    Log JSON parse failure explicitly.

    This ensures failures are visible and not silently ignored.
    """
    retry_msg = " (RETRY FAILED)" if is_retry else ""
    print(f"""
================================================================================
    JSON PARSE FAILURE{retry_msg}
================================================================================

    The LLM response could not be parsed as valid JSON.

    Error: {error}

    Response (first 500 chars):
    {content[:500]}{'...' if len(content) > 500 else ''}

================================================================================
""")


# JSON correction prompt for retry
JSON_CORRECTION_PROMPT = """Your previous response was not valid JSON.

ONLY OUTPUT JSON. No other text, no markdown, no explanation.

Required format:
{
  "tool": null,
  "final": "your message here",
  "memory_write": []
}
"""


def ollama_chat_json(
    model: str,
    messages: list[dict[str, str]],
    base_url: str = DEFAULT_BASE_URL,
    options: Optional[dict] = None,
    timeout_s: int = 120,
    max_retries: int = 1,
) -> dict[str, Any]:
    """
    Chat with Ollama expecting JSON response, with retry on parse failure.

    Uses Ollama's format="json" mode for structured outputs.
    On first JSON parse failure, retries once with correction prompt.
    If still fails, logs failure explicitly and raises ValueError.

    Args:
        model: Model name
        messages: Chat messages
        base_url: Ollama API base URL
        options: Model options
        timeout_s: Request timeout
        max_retries: Number of retry attempts (default 1)

    Returns:
        Parsed agent response dict with tool, final, memory_write

    Raises:
        ValueError: If JSON parsing fails after all retries
    """
    # First attempt with JSON mode enabled
    response = ollama_chat(
        model=model,
        messages=messages,
        base_url=base_url,
        options=options,
        timeout_s=timeout_s,
        format="json",
    )

    content = response.get("message", {}).get("content", "")

    try:
        parsed = parse_agent_response(content)
        return parsed
    except ValueError as first_error:
        if max_retries <= 0:
            _log_json_parse_failure(content, first_error)
            raise

        # Retry with correction prompt
        retry_messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": JSON_CORRECTION_PROMPT},
        ]

        response = ollama_chat(
            model=model,
            messages=retry_messages,
            base_url=base_url,
            options=options,
            timeout_s=timeout_s,
            format="json",
        )

        retry_content = response.get("message", {}).get("content", "")

        try:
            parsed = parse_agent_response(retry_content)
            # Log that retry was needed (not silent success)
            print("WARNING: JSON parse required retry to succeed")
            return parsed
        except ValueError as second_error:
            _log_json_parse_failure(retry_content, second_error, is_retry=True)
            raise ValueError(
                f"JSON parse failed after {max_retries} retry: {second_error}"
            ) from second_error


# Check availability at import time
OLLAMA_AVAILABLE = ollama_healthcheck(timeout_s=2)


# === Simulated Backend for Demo Mode ===

class SimulatedOllamaBackend:
    """Scripted constraint recall from the current prompt, without hidden history.

    This fixture recognizes ToolEnv's constraint and tool-request templates.
    Final answers quote the constraints in MEMORY CONTEXT; quoting a requirement
    measures recall, not whether arbitrary prose actually obeys that requirement.
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def chat(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        import re

        current = messages[-1].get("content", "") if messages else ""
        context = "\n".join(
            message["content"].removeprefix("MEMORY CONTEXT:\n")
            for message in messages[:-1]
            if message.get("content", "").startswith("MEMORY CONTEXT:\n")
        )
        response = {"tool": None, "final": "Acknowledged.", "memory_write": []}
        constraint = re.fullmatch(
            r"Important: when you respond, use (.+) \((.+) requirement\)\.", current
        )
        if constraint:
            value, key = constraint.groups()
            response["final"] = f"I noted the {key} requirement: {value}."
            response["memory_write"] = [{"tag": key, "content": f"{key}: {value}"}]
        elif any(
            word in current.lower()
            for word in (
                "summarize",
                "final answer",
                "complete response",
                "compile everything",
            )
        ):
            response["final"] = context or "No retained requirements are available."
        elif match := re.search(r"(\d+\s*[+*\-]\s*\d+)", current):
            response["tool"] = {"name": "calculator", "args": {"expr": match.group(1)}}
            response["final"] = "Calculating the requested expression."
        elif match := re.search(
            r"(?:know about|information about|Search for) (.+?)[?.]?$", current
        ):
            response["tool"] = {
                "name": "local_search",
                "args": {"query": match.group(1)},
            }
            response["final"] = "Searching the local corpus."
        elif "earlier" in current or "requirement" in current:
            response["final"] = context or "No retained requirements are available."
        return {
            "model": "scripted-constraint-recall",
            "message": {"role": "assistant", "content": json.dumps(response)},
            "done": True,
        }

    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.seed = seed
