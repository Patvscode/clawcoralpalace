"""
weave.py — The Knowledge Weave

Bridges ClawCode execution into the knowledge pipeline.
When an agent completes a coding task, this extracts structured knowledge
and files it into MemPalace automatically.

Usage (as library):
    from weave import capture_task
    capture_task(
        task_desc="Fix YAML parsing bug",
        agent="main",
        task_output=raw_output,
        source_file="memory/2026-04-20.md"
    )

Usage (as CLI):
    python3 weave.py --desc "Fix YAML bug" --agent main --input task_output.txt

When to call it:
    - After any coding task completes (claw-code, exec, codex, etc.)
    - Feed it the raw output from the coding execution
    - It extracts decisions, lessons, patterns and files them into MemPalace
"""

import os
import sys
from pathlib import Path

# Import from local clawcoralpalace
CCP_DIR = Path(__file__).parent
sys.path.insert(0, str(CCP_DIR))

from compactor import extract_knowledge
from mempalace_bridge import capture


# ── Configuration ──────────────────────────────────────────────────────────

# Wing names per agent — each agent gets their own wing in MemPalace
AGENT_WINGS = {
    "main": "main",
    "codex": "codex",
    "gemma": "gemma",
    "q35": "q35",
    "flash": "flash",
    "bob": "bob",
    "alpha": "flash",
    "beta": "prime",
    "gamma": "codex",
    "max": "max",
    "jess": "q35",
}

# What to extract — controls verbosity
EXTRACTION = {
    "decisions": True,
    "lessons": True,
    "code_patterns": True,
    "entities": False,  # KG triples — too heavy for per-task
    "summary": True,
}

# Minimum output length to trigger extraction (avoid noise on tiny outputs)
MIN_OUTPUT_CHARS = 100


# ── Core API ───────────────────────────────────────────────────────────────

def capture_task(
    task_desc: str,
    task_output: str,
    agent: str = "coral",
    source_file: str | None = None,
    use_model: bool = True,
) -> dict:
    """
    Extract knowledge from a completed coding task and file into MemPalace.

    This is the main entry point. Call it after any coding task completes.

    Args:
        task_desc: Short description of what the task was
        task_output: Raw output from the coding execution
        agent: Which agent performed the task
        source_file: Origin file reference (e.g., memory/2026-04-20.md)
        use_model: Use E2B for extraction (True) or regex fallback (False)

    Returns:
        dict with keys: filed, extracted, summary, decisions, lessons, patterns
    """
    wing = AGENT_WINGS.get(agent, agent)
    source = source_file or f"weave/{task_desc[:50]}"

    # Skip tiny outputs — noise filter
    if len(task_output.strip()) < MIN_OUTPUT_CHARS:
        return {
            "filed": 0,
            "extracted": 0,
            "reason": "output too short",
            "summary": "Skipped — output under 100 chars",
        }

    # Extract structured knowledge
    extraction = extract_knowledge(
        task_output,
        task_desc,
        use_model=use_model,
    )

    # File each category into MemPalace
    filed = 0
    total_items = 0

    if EXTRACTION.get("decisions") and extraction.decisions:
        content = "Decisions from task:\n" + "\n".join(
            f"- {d}" for d in extraction.decisions
        )
        r = capture(
            content=content,
            wing=wing,
            room="decisions",
            source_file=source,
            agent_name=agent,
        )
        if r.filed:
            filed += 1
        total_items += len(extraction.decisions)

    if EXTRACTION.get("lessons") and extraction.lessons:
        content = "Lessons from task:\n" + "\n".join(
            f"- {l}" for l in extraction.lessons
        )
        r = capture(
            content=content,
            wing=wing,
            room="lessons",
            source_file=source,
            agent_name=agent,
        )
        if r.filed:
            filed += 1
        total_items += len(extraction.lessons)

    if EXTRACTION.get("code_patterns") and extraction.code_patterns:
        content = "Code patterns from task:\n" + "\n".join(
            f"- {p}" for p in extraction.code_patterns
        )
        r = capture(
            content=content,
            wing=wing,
            room="code",
            source_file=source,
            agent_name=agent,
        )
        if r.filed:
            filed += 1
        total_items += len(extraction.code_patterns)

    # Always file a summary
    if extraction.summary:
        summary_content = f"[{task_desc}] Summary: {extraction.summary}"
        r = capture(
            content=summary_content,
            wing=wing,
            room="summaries",
            source_file=source,
            agent_name=agent,
        )
        if r.filed:
            filed += 1

    return {
        "filed": filed,
        "extracted": total_items,
        "summary": extraction.summary,
        "decisions": len(extraction.decisions),
        "lessons": len(extraction.lessons),
        "patterns": len(extraction.code_patterns),
        "method": extraction.method,
    }


def capture_batch(
    tasks: list[dict],
) -> list[dict]:
    """
    Process multiple tasks at once. Each task is a dict with:
        task_desc, task_output, agent, source_file, use_model

    Returns list of results (one per task).
    """
    return [capture_task(**t) for t in tasks]


def recall_for_task(query: str, agent: str | None = None) -> str:
    """
    Query MemPalace for relevant context before starting a task.

    Args:
        query: What context do we need? (e.g., "YAML parsing patterns")
        agent: Which agent's wing to search (None = all)

    Returns:
        Formatted context string for injection into agent prompt
    """
    from mempalace_bridge import recall as mp_recall

    result = mp_recall(query, wing=agent, limit=5)
    return result.to_context_md() if result.results else ""


# ── CLI Entry Point ────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge weave — extract & file task knowledge")
    parser.add_argument("--desc", required=True, help="Task description")
    parser.add_argument("--input", help="File containing task output (reads stdin if omitted)")
    parser.add_argument("--agent", default="coral", help="Agent name")
    parser.add_argument("--source", help="Source file reference")
    parser.add_argument("--no-model", action="store_true", help="Use regex only (no E2B)")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't file")
    args = parser.parse_args()

    # Read input
    if args.input:
        task_output = Path(args.input).read_text()
    elif not sys.stdin.isatty():
        task_output = sys.stdin.read()
    else:
        print("No --input file and stdin is a TTY. Pipe output or use --input.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        # Just extract, don't file
        extraction = extract_knowledge(task_output, args.desc, use_model=not args.no_model)
        print(f"Method: {extraction.method}")
        print(f"Summary: {extraction.summary}")
        print(f"Decisions: {extraction.decisions}")
        print(f"Lessons: {extraction.lessons}")
        print(f"Patterns: {extraction.code_patterns}")
    else:
        result = capture_task(
            task_desc=args.desc,
            task_output=task_output,
            agent=args.agent,
            source_file=args.source,
            use_model=not args.no_model,
        )
        print(f"Filed: {result['filed']} drawers")
        print(f"Extracted: {result['extracted']} items ({result['decisions']}d/{result['lessons']}l/{result['patterns']}p)")
        print(f"Method: {result['method']}")
        if result.get("summary"):
            print(f"Summary: {result['summary']}")


if __name__ == "__main__":
    main()
