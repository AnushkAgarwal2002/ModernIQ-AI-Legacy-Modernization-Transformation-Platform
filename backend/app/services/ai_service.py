"""
Nebius Token Factory – NVIDIA Nemotron AI Service.

Uses the OpenAI-compatible chat-completions API provided by Nebius Token Factory.

Configuration (backend/.env)
-----------------------------
NEBIUS_API_KEY=<your-nebius-token-factory-api-key>
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1   # default
NEBIUS_MODEL=nvidia/Nemotron-3_5-Lightning               # default

Authentication
--------------
Standard Bearer token: Authorization: Bearer <key>

Never place a real credential in source code or tracked files.
"""
from __future__ import annotations

import json
import logging
import re
import concurrent.futures
import time
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert software architect and legacy modernization specialist.

Your role is to:
1. Analyze legacy codebases thoroughly and honestly
2. Identify technical debt, architectural issues, and modernization opportunities
3. Recommend practical improvements based on the actual code
4. Propose modernized implementations that preserve behavior
5. Generate actionable migration plans

IMPORTANT RULES:
- Base all findings on the actual code provided — never fabricate issues
- If information is unclear or missing, say "Unknown / Requires Further Investigation"
- Never claim AI-generated code is automatically correct — always flag for developer review
- Be specific: cite file names, function names, line numbers where possible
- Prioritize practical, achievable recommendations
- Distinguish between automated assistance and items requiring human judgment

Always respond with valid JSON when instructed to do so."""


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class AIServiceError(Exception):
    """Raised when the AI service cannot complete a request."""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class AIServiceConfigError(AIServiceError):
    """Raised when required configuration (e.g. API key) is missing."""


class AIServiceAuthError(AIServiceError):
    """Raised when the Nebius API key is rejected."""


class AIServiceRateLimitError(AIServiceError):
    """Raised when the Nebius inference endpoint rate-limits this client."""


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Return the Nebius Token Factory API key from settings."""
    key = settings.nebius_api_key
    if not key:
        raise AIServiceConfigError(
            "NEBIUS_API_KEY is not configured. "
            "Create an API key at the Nebius Token Factory console and set "
            "NEBIUS_API_KEY in backend/.env."
        )
    return key


def _inference_url() -> str:
    """Return the base inference URL (without /chat/completions suffix)."""
    url = settings.nebius_base_url or "https://api.tokenfactory.nebius.com/v1"
    return url.rstrip("/")


def _model_id() -> str:
    """Return the configured model identifier."""
    return settings.nebius_model or "nvidia/Nemotron-3_5-Lightning"


def _make_client(api_key: str, read_timeout: float = 240.0) -> httpx.Client:
    """Build an httpx client with Nebius Bearer auth headers."""
    return httpx.Client(
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=5.0),
    )


# ---------------------------------------------------------------------------
# Core call wrapper
# ---------------------------------------------------------------------------

def call_ai(
    messages: List[Dict[str, str]],
    *,
    response_format: str = "text",
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> str:
    """
    POST a chat-completions request to the Nebius Token Factory endpoint and
    return the text of the first choice.

    Parameters
    ----------
    messages:        List of {"role": ..., "content": ...} dicts.
    response_format: "json" to request a JSON object, "text" otherwise.
    temperature:     Sampling temperature (0 = deterministic).
    max_tokens:      Maximum tokens in the completion.

    Raises
    ------
    AIServiceConfigError    – NEBIUS_API_KEY missing or base URL wrong.
    AIServiceAuthError      – Key rejected (401/403).
    AIServiceRateLimitError – Rate limit exceeded (429).
    AIServiceError          – Any other HTTP or parsing failure.
    """
    api_key = _get_api_key()
    base_url = _inference_url()
    endpoint = f"{base_url}/chat/completions"
    model = _model_id()

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    last_exc: Exception = RuntimeError("unreachable")
    for attempt in range(3):
        if attempt:
            time.sleep(2 ** attempt)  # 2 s, then 4 s
        try:
            with _make_client(api_key) as client:
                resp = client.post(endpoint, json=payload)
            break  # success — exit retry loop
        except httpx.RemoteProtocolError as exc:
            last_exc = exc
            logger.warning(
                "Nebius inference disconnected without a response (attempt %d/3): %s",
                attempt + 1, exc,
            )
            continue
        except httpx.ConnectError as exc:
            raise AIServiceConfigError(
                f"Cannot connect to Nebius inference endpoint at {endpoint}. "
                f"Check NEBIUS_BASE_URL in backend/.env. Detail: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIServiceError(
                f"Nebius inference request timed out after 240 seconds at {endpoint}."
            ) from exc
        except Exception as exc:
            raise AIServiceError(
                f"Unexpected error calling Nebius inference: {type(exc).__name__}: {exc}"
            ) from exc
    else:
        raise AIServiceError(
            f"Nebius inference server disconnected without a response after 3 attempts. "
            f"This may indicate an invalid API key, overloaded endpoint, or too many "
            f"concurrent requests. Detail: {last_exc}"
        ) from last_exc

    if resp.status_code == 401:
        try:
            detail = resp.json().get("message", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise AIServiceAuthError(
            f"Nebius Token Factory rejected the API key (401): {detail}. "
            "Verify NEBIUS_API_KEY is a valid, active key in backend/.env."
        )

    if resp.status_code == 403:
        raise AIServiceAuthError(
            f"Nebius Token Factory access denied (403). "
            "The key may not have access to the inference endpoint, "
            f"or the endpoint URL is incorrect. Endpoint: {endpoint}"
        )

    if resp.status_code == 429:
        raise AIServiceRateLimitError(
            "Nebius Token Factory rate limit exceeded (429). Please wait and try again."
        )

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300]
        raise AIServiceError(
            f"Nebius inference request failed with HTTP {resp.status_code}: {detail}"
        )

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if content is None:
            raise AIServiceError("Nebius inference returned a null content field.")
        if not isinstance(content, str) or not content.strip():
            raise AIServiceError(
                f"Nebius inference returned an empty response string. "
                f"Finish reason: {data['choices'][0].get('finish_reason', 'unknown')}"
            )
        return content
    except (KeyError, IndexError) as exc:
        raise AIServiceError(
            f"Unexpected response structure from Nebius inference: {resp.text[:300]}"
        ) from exc


def _extract_json_from_text(text: str) -> str:
    """
    Robustly extract a JSON object from a model response that may be wrapped
    in markdown code fences or prefixed with prose text.
    """
    text = text.strip()

    # Fast path: already starts with a JSON object or array
    if text and text[0] in ('{', '['):
        return text

    # Look for a fenced code block anywhere in the text
    fence_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)(?:\n```|$)', text)
    if fence_match:
        return fence_match.group(1).strip()

    # No fence found — find the first '{' or '[' and return from there
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            return text[i:]

    return text


def _walk_json(text: str):
    """Generator yielding (index, char, in_string) with escape tracking."""
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            yield i, ch, in_string
            continue
        if ch == '\\' and in_string:
            escape_next = True
            yield i, ch, in_string
            continue
        if ch == '"':
            yield i, ch, in_string
            in_string = not in_string
            continue
        yield i, ch, in_string


def _sanitize_json_strings(text: str) -> str:
    """Escape bare control characters inside JSON string values."""
    CONTROL_ESCAPES = {
        '\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f',
    }
    out: List[str] = []
    for _i, ch, in_string in _walk_json(text):
        if in_string and ch in CONTROL_ESCAPES:
            out.append(CONTROL_ESCAPES[ch])
        else:
            out.append(ch)
    return ''.join(out)


def _remove_comments(text: str) -> str:
    """Strip // /* */ and # comments outside JSON string values."""
    out: List[str] = []
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if esc:
            esc = False; out.append(ch); i += 1; continue
        if ch == '\\' and in_str:
            esc = True; out.append(ch); i += 1; continue
        if ch == '"':
            in_str = not in_str; out.append(ch); i += 1; continue
        if in_str:
            out.append(ch); i += 1; continue
        if ch == '/' and i + 1 < n:
            nxt = text[i + 1]
            if nxt == '/':
                i += 2
                while i < n and text[i] != '\n': i += 1
                continue
            if nxt == '*':
                i += 2
                while i < n - 1 and not (text[i] == '*' and text[i + 1] == '/'): i += 1
                i += 2; continue
        if ch == '#':
            i += 1
            while i < n and text[i] != '\n': i += 1
            continue
        out.append(ch); i += 1
    return ''.join(out)


def _remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before '}' or ']'."""
    out: List[str] = []
    pending_comma_idx = -1
    for _i, ch, in_string in _walk_json(text):
        if not in_string and ch != '"':
            if ch == ',':
                pending_comma_idx = len(out)
            elif ch in ('}', ']'):
                if pending_comma_idx >= 0:
                    out[pending_comma_idx] = ''
                    pending_comma_idx = -1
            elif ch not in (' ', '\t', '\n', '\r'):
                pending_comma_idx = -1
        elif ch == '"' and not in_string:
            pending_comma_idx = -1
        out.append(ch)
    return ''.join(out)


def _string_spans(text: str) -> List[tuple]:
    """Return (start, end) ranges for every JSON string literal."""
    spans: List[tuple] = []
    in_str = False; esc = False; str_start = -1
    for i, ch in enumerate(text):
        if esc: esc = False; continue
        if ch == '\\' and in_str: esc = True; continue
        if ch == '"':
            if in_str: spans.append((str_start, i + 1)); in_str = False
            else: str_start = i; in_str = True
    return spans


def _replace_python_literals(text: str) -> str:
    """Replace None/True/False/undefined/... with JSON-valid equivalents."""
    if not text: return text
    spans = _string_spans(text)
    _REPLACEMENTS = {'None': 'null', 'True': 'true', 'False': 'false',
                     'undefined': 'null', '...': 'null', '\u2026': 'null'}
    _PATTERN = re.compile(r'\b(None|True|False|undefined)\b|(\.\.\.)|(…)')
    def _replace(m: re.Match) -> str:
        pos = m.start()
        for start, end in spans:
            if start <= pos < end: return m.group(0)
        return _REPLACEMENTS.get(m.group(0), 'null')
    return _PATTERN.sub(_replace, text)


def _insert_missing_commas(text: str) -> str:
    """Insert commas omitted between adjacent JSON values."""
    if not text: return text
    string_spans = _string_spans(text)
    str_starts = {s for s, _ in string_spans}
    str_ends   = {e for _, e in string_spans}
    in_string_pos: set = set()
    for start, end in string_spans:
        for p in range(start, end): in_string_pos.add(p)
    tokens: List[tuple] = []
    i = 0
    while i < len(text):
        if i in str_starts:
            tokens.append((i, 'S'))
            end = next(e for s, e in string_spans if s == i)
            i = end; continue
        if i not in in_string_pos and text[i] in ('{', '}', '[', ']', ',', ':'):
            tokens.append((i, text[i]))
        i += 1
    VALUE_END   = frozenset(('S', '}', ']'))
    VALUE_START = frozenset(('S', '{', '['))
    CLEARS_NEED = frozenset((',', ':', '{', '['))
    insert_before: List[int] = []
    need_comma = False
    for orig_pos, kind in tokens:
        if kind in VALUE_START and need_comma:
            insert_before.append(orig_pos); need_comma = False
        if kind in CLEARS_NEED: need_comma = False
        elif kind in VALUE_END: need_comma = True
    if not insert_before: return text
    insert_set = set(insert_before)
    result: List[str] = []
    for i, ch in enumerate(text):
        if i in insert_set: result.append(',')
        result.append(ch)
    return ''.join(result)


def _repair_truncated_json(text: str) -> str:
    """Attempt to close unbalanced braces/brackets in truncated JSON."""
    def _json_stack(t: str):
        stack: List[str] = []
        last_safe_pos = 0; last_obj_end = 0
        in_str = False; esc = False
        for i, ch in enumerate(t):
            if esc: esc = False; continue
            if ch == '\\' and in_str: esc = True; continue
            if ch == '"': in_str = not in_str; continue
            if in_str: continue
            if ch in ('{', '['): stack.append(ch)
            elif ch == '}':
                if stack and stack[-1] == '{': stack.pop()
                last_obj_end = i + 1
                if not stack: last_safe_pos = i + 1
            elif ch == ']':
                if stack and stack[-1] == '[': stack.pop()
                if not stack: last_safe_pos = i + 1
        return stack, in_str, last_safe_pos, last_obj_end

    stack, in_string, last_safe_pos, last_obj_end = _json_stack(text)
    if not stack and not in_string:
        return text[:last_safe_pos] if last_safe_pos else text
    if in_string and last_obj_end > 0:
        text = text[:last_obj_end]
        stack, in_string, last_safe_pos, last_obj_end = _json_stack(text)
    closing = ''
    if in_string: closing += '"'
    for opener in reversed(stack):
        closing += '}' if opener == '{' else ']'
    return text + closing


def _call_json(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Dict[str, Any]:
    """
    Call Nebius inference expecting a JSON response, with multi-stage repair.
    """
    raw = call_ai(messages, response_format="text", temperature=temperature, max_tokens=max_tokens)
    text = _extract_json_from_text(raw)

    def _try(t: str) -> Optional[Dict]:
        try: return json.loads(t)
        except json.JSONDecodeError: return None

    result = _try(text)
    if result is not None: return result

    s15 = _remove_comments(text)
    result = _try(s15)
    if result is not None: return result
    base = s15 if s15 != text else text

    s2 = _sanitize_json_strings(base)
    result = _try(s2)
    if result is not None: return result
    base = s2 if s2 != base else base

    s25 = _remove_trailing_commas(base)
    result = _try(s25)
    if result is not None: return result
    base = s25 if s25 != base else base

    s27 = _replace_python_literals(base)
    result = _try(s27)
    if result is not None: return result
    base = s27 if s27 != base else base

    s3 = _insert_missing_commas(base)
    result = _try(s3)
    if result is not None: return result
    base = s3 if s3 != base else base

    s4 = _repair_truncated_json(base)
    result = _try(s4)
    if result is not None: return result

    try:
        json.loads(s4)
    except json.JSONDecodeError as exc:
        logger.error(
            "JSON repair failed after all stages. Error: %s | "
            "Raw preview (first 400 chars): %.400s",
            exc, raw,
        )
        raise AIServiceError(
            f"Nemotron returned malformed JSON that could not be repaired: {exc}. "
            f"Response preview: {raw[:200]}"
        ) from exc
    raise AIServiceError("JSON repair failed")  # pragma: no cover


# ---------------------------------------------------------------------------
# Domain-level AI functions
# ---------------------------------------------------------------------------

def analyze_project(files: List[Dict[str, Any]], project_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive legacy-project analysis via three concurrent Nemotron passes.
    """
    file_listing = "\n".join(
        f"- {f['path']} ({f.get('language', 'unknown')}, {f.get('size_bytes', 0)} bytes)"
        for f in files[:100]
    )

    code_samples: List[str] = []
    for f in files[:15]:
        if f.get("content") and not f.get("is_binary") and f.get("is_supported"):
            code_samples.append(f"=== {f['path']} ===\n{f['content'][:1500]}\n")
        if len(code_samples) >= 8:
            break

    code_context = "\n".join(code_samples)

    project_header = f"""PROJECT INFO:
- Name: {project_info.get('name', 'Unknown')}
- Known Legacy Tech: {project_info.get('legacy_tech', 'Unknown — detect from code')}
- Target Tech: {project_info.get('target_tech', 'Unknown — recommend appropriate target')}
- Objective: {project_info.get('objective', 'Modernize the application')}

FILE STRUCTURE:
{file_listing}

CODE SAMPLES:
{code_context}"""

    pass1_prompt = f"""Analyze this legacy application. Return ONLY raw JSON (no markdown, no fences).

{project_header}

Return exactly this JSON structure:
{{
  "technology_summary": {{
    "languages": [],
    "frameworks": [],
    "libraries": [],
    "runtime_platform": null,
    "build_tools": [],
    "databases": [],
    "external_services": [],
    "apis": [],
    "deployment_assumptions": []
  }},
  "code_structure": {{
    "entry_points": [],
    "modules": [],
    "key_classes": [],
    "key_functions": [],
    "config_files": [],
    "important_files": []
  }},
  "dependencies": {{
    "internal": [],
    "external": [
      {{"name": "example-lib", "version": "1.0.0", "status": "current"}},
      {{"name": "old-framework", "version": "2.3.1", "status": "outdated"}},
      {{"name": "eol-library", "version": "1.2.17", "status": "deprecated"}}
    ],
    "deprecated": ["eol-library 1.x (EOL since 2015)"],
    "risky": ["old-framework 2.x has known CVEs"],
    "coupling_issues": []
  }},
  "architecture": {{
    "pattern": "",
    "description": "",
    "components": [],
    "issues": []
  }},
  "assessment_scores": {{
    "maintainability": {{"score": 0, "rationale": ""}},
    "architecture": {{"score": 0, "rationale": ""}},
    "technology_currency": {{"score": 0, "rationale": ""}},
    "dependency_health": {{"score": 0, "rationale": ""}},
    "security_posture": {{"score": 0, "rationale": ""}},
    "testability": {{"score": 0, "rationale": ""}},
    "documentation": {{"score": 0, "rationale": ""}},
    "coupling": {{"score": 0, "rationale": ""}},
    "migration_complexity": {{"score": 0, "rationale": ""}},
    "modernization_risk": {{"score": 0, "rationale": ""}}
  }},
  "executive_summary": "",
  "target_tech_recommendation": ""
}}

For external dependencies: set "status" to "deprecated" if EOL/abandoned, "outdated" if behind a current major version or has known CVEs, "current" if actively maintained and up-to-date, or "unknown" if unsure. All scores are AI-assisted heuristics (0-100, higher = better health). Base everything strictly on the provided code."""

    pass2a_prompt = f"""Analyze this legacy application for technical debt and modernization opportunities. Return ONLY raw JSON (no markdown, no fences).

{project_header}

Return exactly this JSON structure:
{{
  "technical_debt": [
    {{
      "title": "",
      "description": "",
      "category": "",
      "severity": "critical|high|medium|low",
      "file_path": null,
      "evidence": "",
      "why_matters": "",
      "recommended_action": "",
      "complexity": "high|medium|low",
      "risk": "high|medium|low",
      "priority": 1
    }}
  ],
  "modernization_opportunities": [
    {{
      "title": "",
      "problem": "",
      "evidence": "",
      "proposed_solution": "",
      "category": "Architecture|Dependencies|Security|Performance|Testing|Documentation|Framework|Database|Deployment",
      "priority": "critical|high|medium|low",
      "risk": "high|medium|low",
      "expected_benefit": "",
      "related_files": []
    }}
  ]
}}

Provide exactly 5-7 technical debt items and exactly 5-6 modernization opportunities. Keep each description under 120 words. Base everything strictly on the provided code."""

    pass2b_prompt = f"""Analyze this legacy application and produce an architecture diagram model and a migration plan. Return ONLY raw JSON (no markdown, no fences).

{project_header}

Return exactly this JSON structure:
{{
  "architecture_model": {{
    "current": {{
      "pattern": "",
      "description": "",
      "nodes": [{{"id": "", "label": "", "type": "entrypoint|controller|service|model|database|config|external|frontend|backend|util", "description": ""}}],
      "edges": [{{"source": "", "target": "", "label": "", "type": "dependency|calls|inherits|uses"}}]
    }},
    "recommended": {{
      "pattern": "",
      "description": "",
      "nodes": [{{"id": "", "label": "", "type": "entrypoint|controller|service|model|database|config|external|frontend|backend|util|api|repository|event", "description": ""}}],
      "edges": [{{"source": "", "target": "", "label": "", "type": "dependency|calls|inherits|uses"}}]
    }}
  }},
  "modernization_plan": {{
    "stages": [
      {{
        "name": "",
        "description": "",
        "order": 1,
        "tasks": [
          {{
            "title": "",
            "description": "",
            "related_files": [],
            "priority": "high|medium|low",
            "complexity": "high|medium|low",
            "risk": "high|medium|low",
            "dependencies": [],
            "suggested_order": 1
          }}
        ]
      }}
    ]
  }}
}}

Provide 6-10 nodes per architecture diagram, 4-5 migration stages with 2-4 tasks each. Keep all descriptions under 80 words. Base everything strictly on the provided code."""

    messages1  = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": pass1_prompt}]
    messages2a = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": pass2a_prompt}]
    messages2b = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": pass2b_prompt}]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future1  = executor.submit(_call_json, messages1,  0.2, 4096)
        future2a = executor.submit(_call_json, messages2a, 0.2, 4500)
        result1  = future1.result(timeout=300)
        result2a = future2a.result(timeout=300)
        future2b = executor.submit(_call_json, messages2b, 0.2, 4500)
        result2b = future2b.result(timeout=300)

    return {**result1, **result2a, **result2b}


def transform_file(
    file_path: str,
    original_code: str,
    language: str,
    target_tech: str,
    instruction: Optional[str],
    project_context: str,
) -> Dict[str, Any]:
    """Generate a modernized version of a single source file."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Transform this legacy code to a modern implementation.

PROJECT CONTEXT:
{project_context}

FILE: {file_path}
LANGUAGE: {language}
TARGET TECHNOLOGY: {target_tech}
SPECIFIC INSTRUCTION: {instruction or 'Apply best-practice modernization for the target technology'}

ORIGINAL CODE:
```{language}
{original_code[:8000]}
```

Return raw JSON (no markdown fences):
{{
  "transformed_code": "the complete modernized code",
  "explanation": "detailed explanation of what was changed and why",
  "risks": "potential behavior changes, incompatibilities, or things that may break",
  "review_items": "specific items requiring developer review before accepting this transformation",
  "assumptions": "assumptions made during transformation",
  "validation_notes": "what should be tested/validated"
}}

IMPORTANT:
- Preserve the original behavior unless explicitly asked to change it
- Flag any assumptions you cannot verify from the code alone
- This is a proposal for developer review, not production-ready code
- Do not remove error handling or validation logic"""},
    ]
    return _call_json(messages, temperature=0.1)


def explain_code(
    file_path: str,
    code: str,
    language: str,
    question: Optional[str] = None,
) -> str:
    """Explain what a piece of code does, optionally answering a specific question."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Explain this legacy code clearly and technically.

FILE: {file_path}
LANGUAGE: {language}

CODE:
```{language}
{code[:6000]}
```

{f'SPECIFIC QUESTION: {question}' if question else 'Provide a comprehensive explanation of what this code does, its structure, and any notable issues.'}

Be specific, technical, and honest about any problems you identify."""},
    ]
    return call_ai(messages)


def answer_project_question(
    question: str,
    project_context: str,
    file_context: Optional[str] = None,
    context_type: Optional[str] = None,
) -> str:
    """Answer a contextual question about the modernization project."""
    context_section = ""
    if file_context:
        context_section = f"\nRELEVANT CODE/CONTEXT:\n{file_context[:4000]}\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Answer this question about the legacy modernization project.

PROJECT CONTEXT:
{project_context}
{context_section}
QUESTION: {question}

Provide a specific, technical, actionable answer grounded in the project context.
If you don't have enough information to answer definitively, say so clearly and explain what additional information would help."""},
    ]
    return call_ai(messages, temperature=0.3)


def validate_transformation(
    file_path: str,
    original_code: str,
    transformed_code: str,
) -> Dict[str, Any]:
    """AI-assisted review of a proposed code transformation."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Review this code transformation for correctness and issues.

ORIGINAL ({file_path}):
```
{original_code[:3000]}
```

TRANSFORMED:
```
{transformed_code[:3000]}
```

Return raw JSON (no markdown fences):
{{
  "errors": ["list of definite errors or breaking changes"],
  "warnings": ["list of potential issues or concerns"],
  "manual_review_items": ["specific items that need human review"],
  "static_analysis": [{{"rule": "rule name", "message": "message", "severity": "error|warning|info"}}],
  "overall_assessment": "ready_for_review|issues_detected|requires_significant_rework",
  "notes": "brief overall assessment note"
}}"""},
    ]
    return _call_json(messages)


def _safe_serialize(obj: Any) -> Any:
    """Recursively replace datetime/non-JSON types with strings."""
    from datetime import datetime, date
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_serialize(i) for i in obj]
    return obj


def generate_report(
    project: Dict[str, Any],
    analysis: Dict[str, Any],
    issues: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    transformations: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Synthesize all analysis findings into a comprehensive modernization report."""
    project = _safe_serialize(project)
    analysis = _safe_serialize(analysis)
    issues = _safe_serialize(issues)
    recommendations = _safe_serialize(recommendations)
    transformations = _safe_serialize(transformations)
    plan = _safe_serialize(plan) if plan else None

    summary_data = json.dumps(
        {
            "project": {k: v for k, v in project.items() if k not in ("content", "created_at", "updated_at")},
            "analysis_summary": {
                "technology": analysis.get("technology_summary"),
                "architecture": analysis.get("architecture"),
                "technical_debt_count": len(analysis.get("technical_debt") or []),
            },
            "issues_count": len(issues),
            "high_priority_issues": sum(
                1 for i in issues if i.get("severity") in ("critical", "high")
            ),
            "recommendations_count": len(recommendations),
            "transformations_count": len(transformations),
            "plan_stages": len((plan or {}).get("stages") or []),
        },
        indent=2,
        default=str,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Generate a comprehensive modernization report for this project.

DATA:
{summary_data}

TOP ISSUES:
{json.dumps(issues[:10], indent=2, default=str)}

TOP RECOMMENDATIONS:
{json.dumps(recommendations[:10], indent=2, default=str)}

Return raw JSON (no markdown fences):
{{
  "executive_summary": "2-3 paragraph executive summary",
  "architecture_assessment": "current architecture assessment paragraph",
  "technical_debt_summary": "technical debt narrative",
  "target_architecture": "recommended modern architecture description",
  "migration_plan_summary": "migration approach summary",
  "transformation_summary": "summary of transformations done/proposed",
  "validation_summary": "validation status summary",
  "risks": ["key risk 1", "key risk 2"],
  "manual_review_items": ["item requiring human decision 1", "item 2"]
}}"""},
    ]
    return _call_json(messages)


# ---------------------------------------------------------------------------
# Health / connectivity check
# ---------------------------------------------------------------------------

def check_connectivity() -> Dict[str, Any]:
    """
    Verify that the Nebius Token Factory endpoint is reachable and the API key works.
    Returns a dict with 'status' ('ok' or 'error'), 'message', 'endpoint', and 'model'.
    Never exposes the API key value.
    """
    endpoint = f"{_inference_url()}/chat/completions"
    model = _model_id()
    try:
        result = call_ai(
            [{"role": "user", "content": "Reply with the single word: ready"}],
            temperature=0,
            max_tokens=10,
        )
        return {
            "status": "ok",
            "message": f"Nebius Token Factory reachable. Model: {model}. Response: {result.strip()[:100]}",
            "endpoint": endpoint,
            "model": model,
        }
    except AIServiceConfigError as exc:
        return {"status": "error", "message": str(exc), "endpoint": endpoint, "model": model}
    except AIServiceAuthError as exc:
        return {"status": "error", "message": str(exc), "endpoint": endpoint, "model": model}
    except AIServiceError as exc:
        return {"status": "error", "message": str(exc), "endpoint": endpoint, "model": model}
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Unexpected error: {type(exc).__name__}: {exc}",
            "endpoint": endpoint,
            "model": model,
        }
