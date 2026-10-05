"""LLM access via huggingface_hub.InferenceClient (HF Inference Providers).

Every caller has a deterministic fallback, so the app stays usable with no
token, a cold provider, or a malformed reply.
"""
from __future__ import annotations

import json
import re
from typing import Iterator

from .config import settings

LEVEL_SPECS = {
    0: "Level 0 (The Hook): at most 60 words. The single non-obvious invariant or core mechanism. No preamble.",
    1: "Level 1 (The Anatomy): at most 300 words. Inputs, mechanics, failure modes, trade-offs.",
    2: (
        "Level 2 (The Deep Dive): rigorous and complete. Formal definitions, derivations, "
        "a short code sketch where it clarifies, edge cases, and how it connects to neighbouring ideas."
    ),
}

LENS_SPECS = {
    "core": "Balanced technical exposition.",
    "pattern": (
        "PATTERN lens, for a fast intuitive pattern-matcher. Lead with the shape: the invariant, "
        "the structural parallel in another field, what is preserved under that mapping and exactly "
        "where the analogy breaks. Dense and compressed. Symbols only where they carry the idea."
    ),
    "steps": (
        "STEPS lens, for a careful step-by-step learner. Build from definitions. Define every symbol "
        "before using it. Number the steps; each must follow from the previous with no leaps. "
        "Include one small worked numeric example."
    ),
}

EPISTEMICS = (
    "Epistemic rules: do not invent citations, URLs, page numbers or quotes. Only cite the "
    "provided source material; you may name a widely known canonical text by author and title "
    "if you are certain it exists. If something is uncertain or contested, say so plainly. "
    "Write Markdown; put mathematics in $...$ (inline) or $$...$$ (display)."
)

EXPANSION_SYSTEM = (
    "You are a senior technical educator writing for a sharp adult reader who dislikes fluff, "
    "motivational language and condescension. {level}\n{lens}\n" + EPISTEMICS
)

PRIMER_SYSTEM = """You are an executive context rebuilder for an associative thinker returning to a learning thread after days or weeks away.
Produce a 30-second context reload.
Constraints:
1. No greetings, praise or motivational language.
2. Direct, dense, precise. Use only what is in the provided record; do not invent progress.
3. Output ONLY a JSON object, no prose, matching the schema given."""

PRIMER_USER = """Thread title: {thread_title}
Parent thread / reason for branching: {parent_context}
Units explored (status, deepest level reached, hook text):
{units_explored}

Drop-pins (open loops the user wrote, oldest first):
{pins}

Return JSON:
{{
  "anchor_summary": "one sentence: the core problem or mental model this thread is building",
  "consolidated_points": ["at most 3 short items the user had stabilised"],
  "open_question": "the exact edge, friction or unresolved question to resume from"
}}"""

INGEST_SYSTEM = (
    "You turn source material into a knowledge unit for a microlearning engine used by a "
    "technically literate reader. Stay faithful to the source; do not add claims it does not "
    "support unless they are standard textbook facts. " + EPISTEMICS + "\n"
    "Output ONLY a JSON object, no prose."
)

INGEST_USER = """Source ({kind}): {source_title}
{source_url}

--- SOURCE TEXT (may be truncated) ---
{source_text}
--- END ---

Preferred domain label (may be empty): {domain_hint}

Existing units you may link to (id | title | domain):
{existing}

Return JSON:
{{
  "title": "short concept name",
  "domain": "domain label",
  "l0": "Level 0 hook, <= 60 words",
  "l1": "Level 1 anatomy, <= 300 words, Markdown",
  "probe": {{"prompt": "one recall question that requires explaining, not recognising", "answer": "concise reference answer"}},
  "relations": [{{"target_id": "an id from the list above", "type": "REQUIRES|EXTENDS|ANALOGOUS_TO|CONTRASTS_WITH", "description": "why"}}]
}}
"relations" must only use ids from the list; use [] if none fit. Read "type" as: this unit TYPE target."""

PROBE_SYSTEM = (
    "You write a single active-recall question for a concept. It must require the learner to "
    "produce an explanation or derivation, not recognise a phrase. Output ONLY JSON: "
    '{"prompt": "...", "answer": "concise reference answer"}'
)


class LLMUnavailable(RuntimeError):
    pass


def _client():
    backend = settings.llm_backend
    if backend is None:
        raise LLMUnavailable("No LLM key set (HF_TOKEN or OPENROUTER_API_KEY); LLM features are disabled.")
    from huggingface_hub import InferenceClient

    if backend == "openrouter":
        return InferenceClient(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            timeout=settings.llm_timeout,
            headers={"X-Title": "threads/ microlearning"},
        )
    return InferenceClient(
        provider=settings.inference_provider,
        token=settings.hf_token,
        timeout=settings.llm_timeout,
    )


class ThinkFilter:
    """Drops <think>...</think> spans from a token stream (reasoning models)."""

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            if self.inside:
                end = self.buf.find("</think>")
                if end == -1:
                    self.buf = self.buf[-8:]
                    break
                self.buf = self.buf[end + len("</think>"):]
                self.inside = False
            else:
                start = self.buf.find("<think>")
                if start == -1:
                    # Hold back a possible partial tag at the end.
                    safe = len(self.buf) - 7
                    if safe > 0:
                        out.append(self.buf[:safe])
                        self.buf = self.buf[safe:]
                    break
                out.append(self.buf[:start])
                self.buf = self.buf[start + len("<think>"):]
                self.inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.buf
        self.buf = ""
        return rest


def strip_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.split("</think>")[-1].strip()


def extract_json(text: str) -> dict:
    text = strip_think(text)
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start : end + 1])


REASONING_HEADROOM = 4000  # reasoning tokens count against max_tokens


def _reasoning_kwargs(effort: str, max_tokens: int) -> dict:
    """Reasoning models (e.g. Qwen3.8) think before answering, and the
    thinking is billed against max_tokens: with too small a budget the reply
    is empty (finish_reason=length). Only OpenRouter exposes a uniform switch
    for it; on HF providers we just add headroom when it may be on."""
    if settings.llm_backend == "openrouter":
        if effort == "off":
            return {"max_tokens": max_tokens, "extra_body": {"reasoning": {"enabled": False}}}
        return {"max_tokens": max_tokens + REASONING_HEADROOM, "extra_body": {"reasoning": {"effort": effort}}}
    return {"max_tokens": max_tokens + REASONING_HEADROOM}


def complete(system: str, user: str, max_tokens: int = 1500, temperature: float = 0.3,
             reasoning: str = "off") -> str:
    client = _client()
    out = client.chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=settings.model,
        temperature=temperature,
        **_reasoning_kwargs(reasoning, max_tokens),
    )
    choice = out.choices[0]
    text = strip_think(choice.message.content or "")
    if not text:
        raise RuntimeError(
            f"Model returned no content (finish_reason={choice.finish_reason}); "
            "if 'length', reasoning consumed the token budget."
        )
    return text


def complete_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    # Structured extraction/summary: reasoning off for speed and reliability.
    return extract_json(complete(system, user, max_tokens=max_tokens, temperature=0.2, reasoning="off"))


def stream(system: str, user: str, max_tokens: int = 4000) -> Iterator[str]:
    client = _client()
    filt = ThinkFilter()
    for chunk in client.chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=settings.model,
        temperature=0.4,
        stream=True,
        **_reasoning_kwargs(settings.llm_reasoning, max_tokens),
    ):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if delta:
            piece = filt.feed(delta)
            if piece:
                yield piece
    tail = filt.flush()
    if tail:
        yield tail
