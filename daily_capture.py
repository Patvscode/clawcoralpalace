#!/usr/bin/env python3
"""
daily_capture.py — End-of-day autonomous learning capture

For each agent workspace, reads today's memory/YYYY-MM-DD.md file,
asks Jess (local Qwen 3.6 35B) to extract structured learnings, and
files them into MemPalace.

Designed to run from cron at end of day (e.g. 23:00). Fully autonomous.

Usage:
    python3 daily_capture.py                # capture today for all agents
    python3 daily_capture.py --date 2026-04-20  # specific date
    python3 daily_capture.py --agent main   # specific agent only
    python3 daily_capture.py --dry-run      # show what would be filed
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# Make bridge importable
sys.path.insert(0, "/home/pmello/DevTools/clawcoralpalace")
from mempalace_bridge import capture

# Jess (local Qwen) endpoint
JESS_URL = os.environ.get("JESS_URL", "http://localhost:18080/v1/chat/completions")
JESS_MODEL = os.environ.get("JESS_MODEL", "Qwen3.6-35B-A3B-Q8_0.gguf")

# Agent workspaces to scan
AGENT_WORKSPACES = {
    "main": Path("/home/pmello/.openclaw/workspace-main"),
    "codex": Path("/home/pmello/.openclaw/workspace-codex"),
    "q35": Path("/home/pmello/.openclaw/workspace-q35"),
    "gemma": Path("/home/pmello/.openclaw/workspace-gemma"),
}

# Jess's extraction prompt
EXTRACTION_PROMPT = """You are a knowledge extraction assistant. Analyze the following daily log from an AI agent and extract durable learnings.

Return a JSON object with these keys:
- "decisions": list of concrete decisions made today (strings)
- "lessons": list of lessons learned, mistakes, or "never/always" rules (strings)
- "patterns": list of reusable code/workflow patterns (strings)
- "facts": list of factual discoveries about the system (strings)
- "entities": list of [subject, predicate, object] KG triples for new relationships

Rules:
- Only extract durable knowledge that would help future sessions
- Skip session chatter, greetings, meta-commentary
- Be concise: each item one sentence
- If nothing extractable, return empty lists
- Return ONLY valid JSON, no markdown, no commentary

Daily log:
---
{log}
---

JSON:"""


@dataclass
class DailyExtraction:
    agent: str
    date: str
    decisions: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    entities: list[list[str]] = field(default_factory=list)
    raw_log_chars: int = 0
    error: str | None = None

    def is_empty(self) -> bool:
        return not (self.decisions or self.lessons or self.patterns or self.facts)

    def total_items(self) -> int:
        return len(self.decisions) + len(self.lessons) + len(self.patterns) + len(self.facts)


def call_jess(prompt: str, max_tokens: int = 8000) -> str:
    """Call Jess via OpenAI-compatible API."""
    payload = {
        "model": JESS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,  # Deterministic extraction
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        JESS_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read())
            msg = body["choices"][0]["message"]
            content = msg.get("content") or ""
            # If content is empty but reasoning is present, Qwen sometimes
            # accidentally puts the answer in reasoning_content — try that.
            if not content.strip():
                content = msg.get("reasoning_content") or ""
            return content
    except urllib.error.URLError as e:
        raise RuntimeError(f"Jess unreachable: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Jess response: {e}")


def parse_jess_json(text: str) -> dict:
    """Parse Jess's JSON output, tolerating markdown fences and extra text."""
    text = text.strip()

    # Strip <think>...</think> blocks if they leaked into content
    import re
    text = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
    text = text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first and last fence lines
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Jess returned invalid JSON: {e}\nText: {text[:300]}")


def extract_from_log(agent: str, date: str, log_text: str) -> DailyExtraction:
    """Ask Jess to extract structured learnings from a daily log."""
    result = DailyExtraction(agent=agent, date=date, raw_log_chars=len(log_text))

    # If log is tiny, skip
    if len(log_text) < 200:
        return result

    # Truncate very long logs — Jess can handle 131K context, but keep it sane
    MAX_LOG_CHARS = 60_000
    if len(log_text) > MAX_LOG_CHARS:
        # Keep head + tail
        log_text = log_text[:MAX_LOG_CHARS // 2] + "\n...[middle truncated]...\n" + log_text[-MAX_LOG_CHARS // 2:]

    prompt = EXTRACTION_PROMPT.format(log=log_text)

    try:
        raw = call_jess(prompt)
        parsed = parse_jess_json(raw)

        result.decisions = [str(x) for x in parsed.get("decisions", []) if x]
        result.lessons = [str(x) for x in parsed.get("lessons", []) if x]
        result.patterns = [str(x) for x in parsed.get("patterns", []) if x]
        result.facts = [str(x) for x in parsed.get("facts", []) if x]
        result.entities = [list(x) for x in parsed.get("entities", []) if isinstance(x, list) and len(x) == 3]
    except Exception as e:
        result.error = str(e)

    return result


def file_extraction(extraction: DailyExtraction, dry_run: bool = False) -> dict:
    """File the extracted learnings into MemPalace."""
    results = {
        "agent": extraction.agent,
        "date": extraction.date,
        "filed": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    wing = f"agent_{extraction.agent}"
    source = f"memory/{extraction.date}.md"

    categories = [
        ("decisions", extraction.decisions),
        ("lessons", extraction.lessons),
        ("patterns", extraction.patterns),
        ("facts", extraction.facts),
    ]

    for room, items in categories:
        if not items:
            continue
        content = f"# {extraction.agent} — {room} — {extraction.date}\n\n"
        content += "\n".join(f"- {item}" for item in items)

        if dry_run:
            print(f"  [{extraction.agent}/{room}] Would file {len(items)} items")
            results["filed"] += 1
        else:
            r = capture(
                content=content,
                wing=wing,
                room=room,
                source_file=source,
                agent_name="daily_capture",
            )
            if r.filed:
                results["filed"] += 1
            else:
                results["errors"].append(f"{room}: {r.error}")

    return results


def process_agent(agent: str, date: str, dry_run: bool = False) -> dict:
    """Process one agent's daily log."""
    workspace = AGENT_WORKSPACES.get(agent)
    if not workspace or not workspace.exists():
        return {"agent": agent, "status": "no_workspace"}

    log_file = workspace / "memory" / f"{date}.md"
    if not log_file.exists():
        return {"agent": agent, "status": "no_log"}

    print(f"\n📖 {agent}: reading {log_file}")
    log_text = log_file.read_text()
    print(f"   {len(log_text):,} chars")

    print(f"🧠 {agent}: asking Jess to extract learnings...")
    extraction = extract_from_log(agent, date, log_text)

    if extraction.error:
        print(f"   ❌ {extraction.error}")
        return {"agent": agent, "status": "error", "error": extraction.error}

    if extraction.is_empty():
        print(f"   ℹ️ Nothing extractable")
        return {"agent": agent, "status": "empty"}

    print(f"   ✅ Extracted: "
          f"{len(extraction.decisions)} decisions, "
          f"{len(extraction.lessons)} lessons, "
          f"{len(extraction.patterns)} patterns, "
          f"{len(extraction.facts)} facts, "
          f"{len(extraction.entities)} KG triples")

    # Show samples if dry-run
    if dry_run:
        for cat, items in [("decisions", extraction.decisions),
                           ("lessons", extraction.lessons),
                           ("patterns", extraction.patterns),
                           ("facts", extraction.facts)]:
            for item in items[:2]:
                print(f"     [{cat}] {item[:120]}")

    file_result = file_extraction(extraction, dry_run=dry_run)
    print(f"   📝 Filed: {file_result['filed']} drawers"
          + (f", errors: {file_result['errors']}" if file_result["errors"] else ""))

    return {
        "agent": agent,
        "status": "captured",
        "extraction": {
            "decisions": len(extraction.decisions),
            "lessons": len(extraction.lessons),
            "patterns": len(extraction.patterns),
            "facts": len(extraction.facts),
            "entities": len(extraction.entities),
        },
        "filed": file_result["filed"],
    }


def main():
    parser = argparse.ArgumentParser(description="Daily autonomous learning capture")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="Date to process (YYYY-MM-DD), default: today")
    parser.add_argument("--agent", help="Only process this agent (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract but don't file to MemPalace")
    args = parser.parse_args()

    agents = [args.agent] if args.agent else list(AGENT_WORKSPACES.keys())

    print(f"🪸 Daily Capture — date={args.date} agents={agents}"
          + (" [DRY RUN]" if args.dry_run else ""))

    summary = []
    for agent in agents:
        try:
            result = process_agent(agent, args.date, dry_run=args.dry_run)
            summary.append(result)
        except Exception as e:
            print(f"❌ {agent}: {e}")
            summary.append({"agent": agent, "status": "error", "error": str(e)})

    print("\n" + "=" * 60)
    print("Summary:")
    for s in summary:
        print(f"  {s['agent']:8s}  {s['status']}")
        if s.get("extraction"):
            e = s["extraction"]
            print(f"            {e['decisions']}d/{e['lessons']}l/{e['patterns']}p/{e['facts']}f "
                  f"→ {s.get('filed', 0)} drawers")

    return 0


if __name__ == "__main__":
    sys.exit(main())
