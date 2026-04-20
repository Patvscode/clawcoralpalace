"""
compactor.py — The Compactor (Phase 2)

Smart context compaction that feeds into MemPalace.
Instead of duplicating OpenClaw's built-in compaction, this:
  1. Hooks into the task lifecycle to summarize execution results
  2. Extracts decisions, patterns, and lessons from completed work
  3. Files structured summaries into MemPalace for long-term recall

The key insight: OpenClaw already compacts chat history.
What's missing is *structured knowledge extraction* — turning raw
agent output into searchable, recallable MemPalace drawers.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from mempalace_bridge import capture, CaptureResult


@dataclass
class ExtractionResult:
    """What the compactor extracted from a task's output."""
    decisions: list[str] = field(default_factory=list)
    code_patterns: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    entities: list[tuple[str, str, str]] = field(default_factory=list)  # KG triples
    summary: str = ""


def extract_knowledge(task_output: str, task_description: str = "") -> ExtractionResult:
    """
    Extract structured knowledge from raw task output.

    This uses pattern matching for now. In production, this would
    call a small local model (Gemma E2B on :18081) to do intelligent
    extraction — but the structure is defined here.

    Args:
        task_output: Raw output from claw-code or agent execution
        task_description: What the task was supposed to do

    Returns:
        ExtractionResult with categorized knowledge
    """
    result = ExtractionResult()

    lines = task_output.split("\n")

    for line in lines:
        line_lower = line.lower().strip()

        # Decision detection
        if any(kw in line_lower for kw in [
            "decided to", "chose", "decision:", "went with",
            "approach:", "strategy:", "picked"
        ]):
            result.decisions.append(line.strip())

        # Lesson detection
        if any(kw in line_lower for kw in [
            "lesson:", "learned:", "note to self", "important:",
            "gotcha:", "pitfall:", "watch out", "bug:",
            "never", "always", "must"
        ]):
            result.lessons.append(line.strip())

        # Code pattern detection
        if any(kw in line_lower for kw in [
            "pattern:", "workaround:", "fix:", "solution:",
            "the trick is", "key insight:"
        ]):
            result.code_patterns.append(line.strip())

    # Build summary
    parts = []
    if task_description:
        parts.append(f"Task: {task_description}")
    if result.decisions:
        parts.append(f"Decisions: {'; '.join(result.decisions[:3])}")
    if result.lessons:
        parts.append(f"Lessons: {'; '.join(result.lessons[:3])}")
    result.summary = " | ".join(parts) if parts else "No structured knowledge extracted."

    return result


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
    # Test extraction
    sample = """
    Decided to use subprocess.run instead of Popen for simplicity.
    The trick is to always pass capture_output=True so we get stderr.
    Lesson: Never trust exit code 0 alone — always check stderr for warnings.
    Bug: yaml.safe_load returns None for empty files, not an empty dict.
    Pattern: Use `yaml.safe_load(f) or {}` to handle empty YAML safely.
    """

    result = extract_knowledge(sample, "test YAML parsing task")
    print(f"Summary: {result.summary}")
    print(f"Decisions: {result.decisions}")
    print(f"Lessons: {result.lessons}")
    print(f"Patterns: {result.code_patterns}")
