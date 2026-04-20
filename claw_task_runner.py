"""
claw_task_runner.py — The Scrubber (Phase 1) + Bridge + Compactor integration

Creates isolated worktrees, injects MemPalace context, runs claw-code,
and captures results back into MemPalace.

This is the unified entry point for the CORAL task lifecycle.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from mempalace_bridge import recall, capture, write_diary
from compactor import compact_and_capture, extract_knowledge


def load_task_config(path: str) -> dict:
    """Load task config from YAML or JSON."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        print(f"Error: Task config {path} not found (resolved: {p}).")
        sys.exit(1)

    with open(p) as f:
        text = f.read()

    if p.suffix in (".yaml", ".yml"):
        if yaml is None:
            print("Error: PyYAML not installed. Use JSON or `pip install pyyaml`.")
            sys.exit(1)
        return yaml.safe_load(text) or {}
    else:
        return json.loads(text)


def run_task(
    task_config_path: str,
    scope_files: list[str],
    base_workdir: str = ".",
    skip_recall: bool = False,
    skip_capture: bool = False,
    dry_run: bool = False,
):
    """
    Full CORAL task lifecycle:
    1. Load config
    2. Recall from MemPalace (Phase 3)
    3. Create isolated worktree (Phase 1)
    4. Inject recalled context
    5. Execute claw-code
    6. Capture results into MemPalace (Phase 2+3)
    """
    config = load_task_config(task_config_path)
    task_desc = config.get("description", config.get("task", "unnamed task"))
    wing = config.get("wing", "clawcoralpalace")
    room = config.get("room", "tasks")
    model = config.get("model", "gemma-4-26b")
    entities = config.get("entities", [])
    recall_query = config.get("recall_query", task_desc)

    print(f"🪸 CORAL Task: {task_desc}")
    print(f"   Model: {model} | Wing: {wing} | Room: {room}")

    # ── Step 2: RECALL from MemPalace ──
    recalled_context = None
    if not skip_recall:
        print("🧠 Recalling from MemPalace...")
        try:
            recalled_context = recall(
                query=recall_query,
                wing=wing if wing != "clawcoralpalace" else None,
            )
            if recalled_context.results:
                print(f"   Found {len(recalled_context.results)} results")
            else:
                print("   No prior knowledge found — starting fresh")
        except Exception as e:
            print(f"   ⚠️ Recall failed (continuing without): {e}")

    if dry_run:
        print("\n📋 DRY RUN — would create worktree with:")
        for f in scope_files:
            print(f"   - {f}")
        if recalled_context:
            print("\n📋 Would inject CONTEXT.md:")
            print(recalled_context.to_context_md()[:500])
        return

    # ── Step 3: Create isolated worktree ──
    with tempfile.TemporaryDirectory(prefix="claw_task_") as tmp_dir:
        worktree = Path(tmp_dir) / "worktree"
        worktree.mkdir()

        print(f"📂 Worktree: {worktree}")

        # Symlink scope files
        for file_str in scope_files:
            src = Path(file_str).resolve()
            if src.exists():
                dest = worktree / src.name
                os.symlink(src, dest)
                print(f"   ✅ {src.name}")
            else:
                print(f"   ⚠️ Missing: {file_str}")

        # Symlink instruction files
        for instr_file in ["AGENTS.md", "CLAUDE.md", "CORAL.md"]:
            for search_dir in [Path.cwd(), Path(__file__).parent]:
                candidate = search_dir / instr_file
                if candidate.exists():
                    dest = worktree / instr_file
                    if not dest.exists():
                        os.symlink(candidate, dest)
                        print(f"   ✅ {instr_file} (instruction)")
                    break

        # ── Step 4: Inject recalled context ──
        if recalled_context and recalled_context.results:
            context_md = worktree / "CONTEXT.md"
            context_md.write_text(recalled_context.to_context_md())
            print("   ✅ CONTEXT.md (MemPalace recall)")

        # ── Step 5: Execute ──
        claw_path = os.environ.get("CLAW_PATH", "/home/pmello/bin/claw-code")
        prompt = config.get("prompt", "Execute the task defined in the provided files.")

        cmd = [
            claw_path,
            "--model", model,
            "--permission-mode", "danger-full-access",
            "--output-format", "json",
            "prompt", prompt,
        ]

        print(f"\n🛠️ Executing: {model}")
        start = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=str(worktree),
                capture_output=True,
                text=True,
                timeout=600,  # 10 min max
            )
            elapsed = time.time() - start

            if result.returncode == 0:
                print(f"✨ Completed in {elapsed:.1f}s")
                output = result.stdout
            else:
                print(f"❌ Failed (exit {result.returncode}) in {elapsed:.1f}s")
                output = result.stderr or result.stdout
                print("--- Error ---")
                print(output[:2000])

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            print(f"⏰ Timed out after {elapsed:.1f}s")
            output = "TIMEOUT"
        except FileNotFoundError:
            print(f"❌ claw-code not found at {claw_path}")
            print("   Set CLAW_PATH env var or install claw-code")
            output = "CLAW_CODE_NOT_FOUND"

        # ── Step 6: Capture results into MemPalace ──
        if not skip_capture and output and output not in ("TIMEOUT", "CLAW_CODE_NOT_FOUND"):
            print("\n📝 Capturing to MemPalace...")
            try:
                captures = compact_and_capture(
                    task_output=output,
                    task_description=task_desc,
                    wing=wing,
                    room=room,
                    agent_name="coral",
                    source_file=task_config_path,
                )
                filed = sum(1 for c in captures if c.filed)
                failed = sum(1 for c in captures if c.error)
                print(f"   Filed: {filed}/{len(captures)} drawers" +
                      (f" ({failed} errors)" if failed else ""))
            except Exception as e:
                print(f"   ⚠️ Capture failed: {e}")

            # Diary entry
            write_diary(
                agent_name="coral",
                entry=f"TASK:{task_desc}|model={model}|elapsed={elapsed:.0f}s|"
                      f"status={'ok' if result.returncode == 0 else 'fail'}",
                topic="task",
            )

        # ── Step 7: Report ──
        print("\n" + "=" * 60)
        print(f"🪸 CORAL Task Complete: {task_desc}")
        if output and output not in ("TIMEOUT", "CLAW_CODE_NOT_FOUND"):
            # Print a truncated summary
            summary_lines = output.strip().split("\n")
            if len(summary_lines) > 20:
                for line in summary_lines[:10]:
                    print(f"   {line}")
                print(f"   ... ({len(summary_lines) - 20} lines omitted)")
                for line in summary_lines[-10:]:
                    print(f"   {line}")
            else:
                for line in summary_lines:
                    print(f"   {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CORAL Task Runner — Scrubber + MemPalace Bridge + Compactor"
    )
    parser.add_argument("config", help="Path to task config (YAML or JSON)")
    parser.add_argument("--scope", nargs="+", help="Files to include in worktree", required=True)
    parser.add_argument("--workdir", default=".", help="Base directory for relative paths")
    parser.add_argument("--skip-recall", action="store_true", help="Skip MemPalace recall step")
    parser.add_argument("--skip-capture", action="store_true", help="Skip MemPalace capture step")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, don't execute")

    args = parser.parse_args()
    run_task(
        args.config,
        args.scope,
        args.workdir,
        skip_recall=args.skip_recall,
        skip_capture=args.skip_capture,
        dry_run=args.dry_run,
    )
