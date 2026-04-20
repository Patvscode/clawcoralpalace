"""
mempalace_bridge.py — The Bridge (Phase 3)

Connects CORAL task lifecycle to MemPalace for knowledge recall and capture.
Two main operations:
  - recall(query, wing, room) → retrieves relevant context for task injection
  - capture(content, wing, room, entities) → files results back into MemPalace + KG
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# MemPalace MCP tool names (called via mcporter or direct MCP)
MEMPALACE_TOOLS = {
    "search": "mempalace__mempalace_search",
    "add": "mempalace__mempalace_add_drawer",
    "kg_query": "mempalace__mempalace_kg_query",
    "kg_add": "mempalace__mempalace_kg_add",
    "diary_write": "mempalace__mempalace_diary_write",
    "check_dup": "mempalace__mempalace_check_duplicate",
}

MAX_RECALL_TOKENS = 2000  # Hard cap on injected context size
MAX_RECALL_RESULTS = 5


@dataclass
class RecalledContext:
    """Container for context retrieved from MemPalace."""
    query: str
    results: list[dict] = field(default_factory=list)
    kg_facts: list[dict] = field(default_factory=list)
    total_chars: int = 0

    def to_context_md(self) -> str:
        """Format recalled context as CONTEXT.md for worktree injection."""
        lines = [
            "# Recalled Context (from MemPalace)",
            f"_Query: {self.query}_",
            "",
        ]

        if self.kg_facts:
            lines.append("## Known Relationships")
            for fact in self.kg_facts:
                subj = fact.get("subject", "?")
                pred = fact.get("predicate", "?")
                obj = fact.get("object", "?")
                lines.append(f"- {subj} → {pred} → {obj}")
            lines.append("")

        if self.results:
            lines.append("## Prior Knowledge")
            for i, r in enumerate(self.results, 1):
                content = r.get("content", "")
                wing = r.get("wing", "unknown")
                room = r.get("room", "unknown")
                score = r.get("score", 0)
                # Truncate individual results to keep total under budget
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"### [{i}] {wing}/{room} (score: {score:.2f})")
                lines.append(content)
                lines.append("")

        output = "\n".join(lines)

        # Hard truncation at token budget (rough: 1 token ≈ 4 chars)
        max_chars = MAX_RECALL_TOKENS * 4
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n_[truncated — context budget reached]_"

        return output


def recall(
    query: str,
    wing: Optional[str] = None,
    room: Optional[str] = None,
    entities: Optional[list[str]] = None,
    limit: int = MAX_RECALL_RESULTS,
) -> RecalledContext:
    """
    Query MemPalace for task-relevant context.

    Args:
        query: Natural language description of what we need
        wing: Optional wing filter (project name)
        room: Optional room filter (topic)
        entities: Optional entity names to query KG for
        limit: Max number of search results

    Returns:
        RecalledContext with formatted results ready for injection
    """
    ctx = RecalledContext(query=query)

    # 1. Semantic search
    search_args = {"query": query, "limit": limit}
    if wing:
        search_args["wing"] = wing
    if room:
        search_args["room"] = room

    try:
        results = _call_mempalace("search", search_args)
        if results and "results" in results:
            ctx.results = results["results"]
    except Exception as e:
        print(f"⚠️ MemPalace search failed: {e}", file=sys.stderr)

    # 2. KG queries for named entities
    if entities:
        for entity in entities:
            try:
                kg = _call_mempalace("kg_query", {"entity": entity})
                if kg and "facts" in kg:
                    ctx.kg_facts.extend(kg["facts"])
            except Exception as e:
                print(f"⚠️ KG query for '{entity}' failed: {e}", file=sys.stderr)

    ctx.total_chars = len(ctx.to_context_md())
    return ctx


@dataclass
class CaptureResult:
    """Result of capturing knowledge back into MemPalace."""
    drawer_id: Optional[str] = None
    kg_facts_added: int = 0
    duplicate: bool = False


def capture(
    content: str,
    wing: str,
    room: str,
    entities: Optional[list[tuple[str, str, str]]] = None,
    source_file: Optional[str] = None,
    agent_name: str = "coral",
) -> CaptureResult:
    """
    File knowledge back into MemPalace after task completion.

    Args:
        content: The knowledge to store (verbatim)
        wing: Project/domain wing
        room: Topic room
        entities: Optional KG triples as (subject, predicate, object)
        source_file: Where this knowledge came from
        agent_name: Which agent is filing this

    Returns:
        CaptureResult with filing details
    """
    result = CaptureResult()

    # 1. Check for duplicates first
    try:
        dup_check = _call_mempalace("check_dup", {"content": content, "threshold": 0.85})
        if dup_check and dup_check.get("is_duplicate"):
            result.duplicate = True
            print(f"ℹ️ Duplicate detected, skipping drawer filing", file=sys.stderr)
            # Still add KG facts even if content is duplicate
        else:
            # 2. File the drawer
            add_args = {
                "wing": wing,
                "room": room,
                "content": content,
                "added_by": agent_name,
            }
            if source_file:
                add_args["source_file"] = source_file

            add_result = _call_mempalace("add", add_args)
            if add_result:
                result.drawer_id = add_result.get("drawer_id")
    except Exception as e:
        print(f"⚠️ MemPalace capture failed: {e}", file=sys.stderr)

    # 3. Add KG facts
    if entities:
        for subj, pred, obj in entities:
            try:
                _call_mempalace("kg_add", {
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                })
                result.kg_facts_added += 1
            except Exception as e:
                print(f"⚠️ KG add ({subj}→{pred}→{obj}) failed: {e}", file=sys.stderr)

    return result


def write_diary(agent_name: str, entry: str, topic: str = "task") -> bool:
    """Write a diary entry for the agent in AAAK format."""
    try:
        _call_mempalace("diary_write", {
            "agent_name": agent_name,
            "entry": entry,
            "topic": topic,
        })
        return True
    except Exception as e:
        print(f"⚠️ Diary write failed: {e}", file=sys.stderr)
        return False


def _call_mempalace(tool: str, args: dict) -> Optional[dict]:
    """
    Call a MemPalace MCP tool.

    This uses mcporter CLI for now. In production, this would use
    the MCP protocol directly or OpenClaw's built-in MCP bridge.
    """
    tool_name = MEMPALACE_TOOLS.get(tool, tool)

    # Try mcporter first
    cmd = [
        "mcporter", "call",
        "--server", "mempalace",
        "--tool", tool_name,
        "--args", json.dumps(args),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        else:
            # Fallback: try direct HTTP if mcporter isn't available
            print(f"mcporter failed ({result.returncode}), trying fallback", file=sys.stderr)
            return _call_mempalace_http(tool_name, args)
    except FileNotFoundError:
        return _call_mempalace_http(tool_name, args)
    except subprocess.TimeoutExpired:
        print(f"⚠️ MemPalace call timed out: {tool}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        return {}


def _call_mempalace_http(tool_name: str, args: dict) -> Optional[dict]:
    """Fallback: call MemPalace via its HTTP MCP endpoint if available."""
    import urllib.request
    import urllib.error

    url = "http://localhost:8200/mcp/call"  # Default MemPalace MCP port
    payload = json.dumps({"tool": tool_name, "arguments": args}).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"⚠️ HTTP fallback failed: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    # Quick test: recall something
    import sys
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        ctx = recall(query)
        print(ctx.to_context_md())
    else:
        print("Usage: python mempalace_bridge.py <query>")
        print("Example: python mempalace_bridge.py 'how does the scrubber work'")
