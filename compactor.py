"""
compactor.py — The Compactor (Phase 2 + Phase 5b)

Smart context compaction that feeds into MemPalace.
Instead of duplicating OpenClaw's built-in compaction, this:
  1. Hooks into the task lifecycle to summarize execution results
  2. Extracts decisions, patterns, and lessons from completed work
  3. Files structured summaries into MemPalace for long-term recall

The key insight: OpenClaw already compacts chat history.
What's missing is *structured knowledge extraction* — turning raw
agent output into searchable, recallable MemPalace drawers.

Phase 5b: Primary extraction path is Gemma E2B on :18081 (dedicated helper,
fast, always-on). Falls back to regex pattern matching if E2B is unreachable
or returns invalid JSON.
"""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from mempalace_bridge import capture, CaptureResult

# Gemma E2B endpoint (dedicated compactor helper, port 18081)
E2B_URL = os.environ.get(
    "E2B_URL", "http://localhost:18081/v1/chat/completions"
)
E2B_MODEL = os.environ.get("E2B_MODEL", "gemma-4-E2B-it-Q8_0.gguf")
E2B_TIMEOUT = int(os.environ.get("E2B_TIMEOUT", "60"))

EXTRACTION_PROMPT = """You are a knowledge extraction assistant. Analyze this task output and extract durable learnings.

Return ONLY valid JSON (no markdown, no commentary) with these keys:
- "decisions": list of concrete decisions made (strings)
- "lessons": list of lessons, gotchas, or never/always rules (strings)
- "code_patterns": list of reusable code/workflow patterns (strings)
- "summary": one-sentence overall summary (string)

Rules:
- Only include items that would genuinely help future work.
- Skip greetings, chatter, meta-commentary.
- Each item: one concise sentence.
- If nothing extractable, return empty lists and a brief summary.

Task: {task_description}

Output:
---
{task_output}
---

JSON:"""



@dataclass
class ExtractionResult:
    """What the compactor extracted from a task's output."""
    decisions: list[str] = field(default_factory=list)
    code_patterns: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    entities: list[tuple[str, str, str]] = field(default_factory=list)  # KG triples
    summary: str = ""
    method: str = "regex"  # "e2b" or "regex"


def _call_e2b(prompt: str, max_tokens: int = 2048) -> str:
    """Call Gemma E2B via OpenAI-compatible API. Raises on failure."""
    payload = {
        "model": E2B_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        E2B_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=E2B_TIMEOUT) as resp:
        body = json.loads(resp.read())
        msg = body["choices"][0]["message"]
        content = msg.get("content") or ""
        if not content.strip():
            content = msg.get("reasoning_content") or ""
        return content


def _parse_json_lenient(text: str) -> dict:
    """Parse JSON tolerating fences, <think> blocks, and surrounding prose."""
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _extract_via_e2b(task_output: str, task_description: str) -> Optional[ExtractionResult]:
    """Try Gemma E2B extraction. Returns None on any failure (fall back to regex)."""
    # Truncate very long output — keep head + tail
    MAX_CHARS = 40_000
    if len(task_output) > MAX_CHARS:
        half = MAX_CHARS // 2
        task_output = (
            task_output[:half]
            + "\n...[middle truncated]...\n"
            + task_output[-half:]
        )

    prompt = EXTRACTION_PROMPT.format(
        task_description=task_description or "(unspecified)",
        task_output=task_output,
    )
    try:
        raw = _call_e2b(prompt)
        parsed = _parse_json_lenient(raw)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, RuntimeError) as e:
        # Network, parse, or shape failure — caller falls back to regex
        return None

    result = ExtractionResult(method="e2b")
    result.decisions = [str(x) for x in parsed.get("decisions", []) if x]
    result.lessons = [str(x) for x in parsed.get("lessons", []) if x]
    result.code_patterns = [str(x) for x in parsed.get("code_patterns", []) if x]
    summary = parsed.get("summary") or ""
    if task_description and not summary:
        summary = f"Task: {task_description}"
    result.summary = str(summary).strip()
    return result


def _extract_via_regex(task_output: str, task_description: str = "") -> ExtractionResult:
    """Legacy regex fallback — used when E2B is unreachable or invalid.
    
    Each line is matched to at most ONE category (priority: decisions > lessons > patterns).
    """
    result = ExtractionResult(method="regex")

    for line in task_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        line_lower = line.lower()

        # Priority: decisions > lessons > patterns (first match wins)
        matched = False

        if any(kw in line_lower for kw in [
            "decided to", "chose", "decision:", "went with",
            "approach:", "strategy:", "picked"
        ]):
            # Make sure this line isn't also a lesson/keyword line
            if not any(kw in line_lower for kw in [
                "lesson:", "learned:", "note to self", "important:",
                "gotcha:", "pitfall:", "watch out", "bug:",
                "never", "always", "must", "pattern:", "workaround:",
                "fix:", "solution:", "the trick is", "key insight:"
            ]):
                result.decisions.append(line)
                matched = True

        if not matched and any(kw in line_lower for kw in [
            "lesson:", "learned:", "note to self", "important:",
            "gotcha:", "pitfall:", "watch out", "bug:",
            "never", "always", "must"
        ]):
            result.lessons.append(line)
            matched = True

        if not matched and any(kw in line_lower for kw in [
            "pattern:", "workaround:", "fix:", "solution:",
            "the trick is", "key insight:"
        ]):
            result.code_patterns.append(line)
            matched = True

    parts = []
    if task_description:
        parts.append(f"Task: {task_description}")
    if result.decisions:
        parts.append(f"Decisions: {'; '.join(result.decisions[:3])}")
    if result.lessons:
        parts.append(f"Lessons: {'; '.join(result.lessons[:3])}")
    result.summary = " | ".join(parts) if parts else "No structured knowledge extracted."
    return result


def extract_knowledge(
    task_output: str,
    task_description: str = "",
    use_model: bool = True,
) -> ExtractionResult:
    """
    Extract structured knowledge from raw task output.

    Phase 5b: Primary path calls Gemma E2B (:18081) for model-powered
    extraction. Falls back to regex pattern matching if E2B is
    unreachable or returns invalid JSON.

    Args:
        task_output: Raw output from claw-code or agent execution
        task_description: What the task was supposed to do
        use_model: If False, skip E2B and go straight to regex (useful for tests)

    Returns:
        ExtractionResult with categorized knowledge and `.method`
        set to either "e2b" or "regex".
    """
    if use_model and task_output.strip():
        result = _extract_via_e2b(task_output, task_description)
        if result is not None:
            return result
    return _extract_via_regex(task_output, task_description)


def compact_and_capture(
    task_output: str,
    task_description: str,
    wing: str,
    room: str = "decisions",
    agent_name: str = "coral",
    source_file: Optional[str] = None,
) -> list[CaptureResult]:
    """
    Full compaction pipeline: extract → file into MemPalace.

    Args:
        task_output: Raw output from task execution
        task_description: What the task was about
        wing: MemPalace wing (project name)
        room: Default room for filing
        agent_name: Who's filing
        source_file: Origin file reference

    Returns:
        List of CaptureResults for each filing
    """
    extraction = extract_knowledge(task_output, task_description)
    results = []

    # File decisions
    if extraction.decisions:
        content = f"[{task_description}] Decisions:\n" + "\n".join(
            f"- {d}" for d in extraction.decisions
        )
        r = capture(
            content=content,
            wing=wing,
            room="decisions",
            source_file=source_file,
            agent_name=agent_name,
        )
        results.append(r)

    # File lessons
    if extraction.lessons:
        content = f"[{task_description}] Lessons:\n" + "\n".join(
            f"- {l}" for l in extraction.lessons
        )
        r = capture(
            content=content,
            wing=wing,
            room="lessons",
            source_file=source_file,
            agent_name=agent_name,
        )
        results.append(r)

    # File code patterns
    if extraction.code_patterns:
        content = f"[{task_description}] Patterns:\n" + "\n".join(
            f"- {p}" for p in extraction.code_patterns
        )
        r = capture(
            content=content,
            wing=wing,
            room="code",
            source_file=source_file,
            agent_name=agent_name,
        )
        results.append(r)

    # File summary even if nothing specific was extracted
    if not results and extraction.summary:
        r = capture(
            content=extraction.summary,
            wing=wing,
            room=room,
            source_file=source_file,
            agent_name=agent_name,
        )
        results.append(r)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compactor smoke test")
    parser.add_argument("--no-model", action="store_true", help="Skip E2B, use regex only")
    args = parser.parse_args()

    sample = """
    Decided to use subprocess.run instead of Popen for simplicity.
    The trick is to always pass capture_output=True so we get stderr.
    Lesson: Never trust exit code 0 alone — always check stderr for warnings.
    Bug: yaml.safe_load returns None for empty files, not an empty dict.
    Pattern: Use `yaml.safe_load(f) or {}` to handle empty YAML safely.
    """

    result = extract_knowledge(
        sample, "test YAML parsing task", use_model=not args.no_model
    )
    print(f"Method:    {result.method}")
    print(f"Summary:   {result.summary}")
    print(f"Decisions: {result.decisions}")
    print(f"Lessons:   {result.lessons}")
    print(f"Patterns:  {result.code_patterns}")
