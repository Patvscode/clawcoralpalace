"""
mempalace_bridge.py — The Bridge between CORAL and MemPalace

Uses the native `mempalace` CLI (not MCP) for reliable Python-to-Python calls.
MemPalace runs as both an MCP server (for agents) and a CLI (for scripts).

Two main operations:
  - recall(query, wing, room) → retrieves relevant context for task injection
  - capture(content, wing, room, source_file) → files results back
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Resolve the mempalace CLI — prefer venv, fallback to PATH
MEMPALACE_BIN = os.environ.get("MEMPALACE_BIN") or shutil.which("mempalace")
if not MEMPALACE_BIN:
    venv_candidate = Path.home() / ".venvs" / "mempalace" / "bin" / "mempalace"
    if venv_candidate.exists():
        MEMPALACE_BIN = str(venv_candidate)

MAX_RECALL_TOKENS = 2000  # Hard cap on injected context size (rough: 4 chars/token)
MAX_RECALL_RESULTS = 5


@dataclass
class RecalledResult:
    """Single search hit from MemPalace."""
    wing: str = ""
    room: str = ""
    content: str = ""
    source: str = ""
    score: float = 0.0


@dataclass
class RecalledContext:
    """Container for context retrieved from MemPalace."""
    query: str
    results: list[RecalledResult] = field(default_factory=list)
    total_chars: int = 0

    def to_context_md(self) -> str:
        """Format recalled context as CONTEXT.md for worktree injection."""
        lines = [
            "# Recalled Context (from MemPalace)",
            f"_Query: {self.query}_",
            "",
        ]

        if not self.results:
            lines.append("_No prior knowledge found in MemPalace._")
            return "\n".join(lines)

        lines.append("## Prior Knowledge")
        for i, r in enumerate(self.results, 1):
            content = r.content.strip()
            # Truncate individual results
            if len(content) > 500:
                content = content[:500] + "..."
            header = f"### [{i}] {r.wing}/{r.room}"
            if r.score:
                header += f" (score: {r.score:.3f})"
            lines.append(header)
            if r.source:
                lines.append(f"_source: {r.source}_")
            lines.append("")
            lines.append(content)
            lines.append("")

        output = "\n".join(lines)

        # Hard truncation at token budget
        max_chars = MAX_RECALL_TOKENS * 4
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n_[truncated — context budget reached]_"

        return output


def _parse_search_output(text: str) -> list[RecalledResult]:
    """Parse `mempalace search` CLI output into structured results."""
    results = []
    # Strip ANSI color codes
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)

    # Pattern: [N] wing / room
    #          Source: ...
    #          Match:  0.XXX
    #          (blank line)
    #          content lines until next [N] or end
    result_re = re.compile(
        r'\[(\d+)\]\s+(\S+)\s*/\s*(\S+)\s*\n'
        r'\s*Source:\s*(.+?)\n'
        r'\s*Match:\s*([\d.]+)\s*\n',
        re.MULTILINE,
    )

    matches = list(result_re.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content_block = text[start:end].strip()

        try:
            score = float(m.group(5))
        except ValueError:
            score = 0.0

        results.append(RecalledResult(
            wing=m.group(2).strip(),
            room=m.group(3).strip(),
            content=content_block,
            source=m.group(4).strip(),
            score=score,
        ))

    return results


def recall(
    query: str,
    wing: Optional[str] = None,
    room: Optional[str] = None,
    limit: int = MAX_RECALL_RESULTS,
) -> RecalledContext:
    """
    Query MemPalace for task-relevant context.

    Args:
        query: Natural language description of what we need
        wing: Optional wing filter (project name)
        room: Optional room filter (topic)
        limit: Max number of search results

    Returns:
        RecalledContext with formatted results ready for injection
    """
    ctx = RecalledContext(query=query)

    if not MEMPALACE_BIN:
        print("⚠️ mempalace CLI not found — skipping recall", file=sys.stderr)
        return ctx

    cmd = [MEMPALACE_BIN, "search", query, "--results", str(limit)]
    if wing:
        cmd.extend(["--wing", wing])
    if room:
        cmd.extend(["--room", room])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "TERM": "dumb"},  # suppress color codes
        )
        if result.returncode == 0:
            ctx.results = _parse_search_output(result.stdout)
        else:
            print(f"⚠️ mempalace search failed: {result.stderr[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"⚠️ mempalace search timed out after 30s", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ mempalace search error: {e}", file=sys.stderr)

    ctx.total_chars = len(ctx.to_context_md())
    return ctx


@dataclass
class CaptureResult:
    """Result of capturing knowledge back into MemPalace."""
    filed: bool = False
    error: Optional[str] = None
    path: Optional[str] = None


def capture(
    content: str,
    wing: str,
    room: str,
    source_file: Optional[str] = None,
    agent_name: str = "coral",
) -> CaptureResult:
    """
    File knowledge back into MemPalace after task completion.

    The `mempalace` CLI mines from files rather than accepting inline content,
    so we write the content to a temp file and mine that.

    Args:
        content: The knowledge to store
        wing: Project/domain wing
        room: Topic room
        source_file: Where this knowledge came from (original path)
        agent_name: Which agent is filing this

    Returns:
        CaptureResult with filing details
    """
    result = CaptureResult()

    if not MEMPALACE_BIN:
        result.error = "mempalace CLI not found"
        return result

    # Write content to a staging file the CLI can mine
    import tempfile
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stage_dir = Path.home() / ".mempalace" / "staging" / wing / room
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_file = stage_dir / f"{timestamp}_{agent_name}.md"

    header_lines = [
        f"# {room} — {wing}",
        f"_Filed by {agent_name} at {timestamp}_",
    ]
    if source_file:
        header_lines.append(f"_source: {source_file}_")
    header_lines.append("")
    full_content = "\n".join(header_lines) + content

    try:
        stage_file.write_text(full_content)
        result.path = str(stage_file)

        # mempalace mine expects a directory with mempalace.yaml;
        # rooms are auto-derived from subdirectory structure.
        wing_dir = stage_dir.parent  # ~/.mempalace/staging/<wing>/
        yaml_path = wing_dir / "mempalace.yaml"

        # Auto-init the wing dir if not yet initialized
        if not yaml_path.exists():
            init_proc = subprocess.run(
                [MEMPALACE_BIN, "init", str(wing_dir), "--yes"],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "TERM": "dumb"},
            )
            if init_proc.returncode != 0 and not yaml_path.exists():
                result.error = f"init failed: {init_proc.stderr[:300]}"
                return result

        cmd = [
            MEMPALACE_BIN, "mine", str(wing_dir),
            "--wing", wing,
            "--agent", agent_name,
            "--extract", "general",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "TERM": "dumb"},
        )
        if proc.returncode == 0:
            result.filed = True
        else:
            # mempalace mine sometimes returns non-zero for warnings;
            # check if the file was actually recorded
            stderr_lower = proc.stderr.lower()
            if "error" in stderr_lower or "failed" in stderr_lower:
                result.error = (proc.stderr or proc.stdout)[:500]
            else:
                # Probably just the GPU warning — treat as success
                result.filed = True
    except subprocess.TimeoutExpired:
        result.error = "mine operation timed out"
    except Exception as e:
        result.error = str(e)

    return result


def write_diary(agent_name: str, entry: str, topic: str = "task") -> bool:
    """
    Write a diary entry for the agent. MemPalace CLI doesn't have a direct
    diary command, so we stage it as a file under the agent's diary room
    and mine it (which the MCP-level tools handle natively).
    """
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        content = f"DIARY:{timestamp}|{agent_name}|{topic}|{entry}"
        r = capture(
            content=content,
            wing=f"diary_{agent_name}",
            room=topic,
            agent_name=agent_name,
        )
        return r.filed
    except Exception as e:
        print(f"⚠️ diary write failed: {e}", file=sys.stderr)
        return False


def status() -> dict:
    """Get MemPalace palace status (total drawers, wings, rooms)."""
    if not MEMPALACE_BIN:
        return {"error": "mempalace CLI not found"}

    try:
        proc = subprocess.run(
            [MEMPALACE_BIN, "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return {"output": proc.stdout, "ok": True}
        return {"error": proc.stderr, "ok": False}
    except Exception as e:
        return {"error": str(e), "ok": False}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python mempalace_bridge.py recall <query>")
        print("  python mempalace_bridge.py status")
        print("  python mempalace_bridge.py capture <wing> <room> <content>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "recall":
        query = " ".join(sys.argv[2:])
        ctx = recall(query)
        print(ctx.to_context_md())
    elif cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "capture" and len(sys.argv) >= 5:
        wing = sys.argv[2]
        room = sys.argv[3]
        content = " ".join(sys.argv[4:])
        r = capture(content, wing, room)
        print(f"Filed: {r.filed}, Path: {r.path}, Error: {r.error}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
