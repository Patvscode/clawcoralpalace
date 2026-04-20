# clawcoralpalace ⚡

The knowledge pipeline for OpenClaw — extracts, files, and recalls learnings from every coding task.

## Quick Start

```bash
# Per-task knowledge capture (after any coding task)
python3 weave.py --desc "Fix YAML parsing bug" --input task_output.txt --agent main

# Dry run (extract only, don't file)
python3 weave.py --desc "Fix YAML parsing bug" --input task_output.txt --agent main --dry-run

# Autonomous daily capture (runs 23:00 nightly)
python3 daily_capture.py --agent main --date 2026-04-20
```

## How It Works

```
Agent codes (claw-code, exec, codex, etc.)
    ↓
weave.py extracts structured knowledge → files into MemPalace
    ↓
MemPalace stores decisions, lessons, patterns, facts
    ↓
Future tasks recall relevant context before starting
    ↓
System gets better over time
```

**Two capture modes:**
- **Per-task** (`weave.py`) — real-time extraction after coding tasks
- **Daily** (`daily_capture.py`) — nightly batch extraction from agent daily logs

## Components

| File | Role | Status |
|------|------|--------|
| `weave.py` | Main API — extract & file task knowledge | ✅ Working |
| `compactor.py` | Knowledge extraction (E2B + regex fallback) | ✅ Working |
| `mempalace_bridge.py` | Recall/capture via MemPalace CLI | ✅ Working |
| `daily_capture.py` | Nightly autonomous learning (23:00) | ✅ Working |
| `claw_task_runner.py` | Legacy CORAL task runner (manual CLI) | ⚠️ Dead-end |
| `coral_task/` | Standalone CORAL grading experiment | ✅ Working (isolated) |

## What's Actually Working

- **Compactor** — Gemma E2B on :18081 extracts clean structured JSON. Falls back to regex on failure.
- **Daily capture** — Reads each agent's `memory/YYYY-MM-DD.md`, asks Jess on :18080 to extract learnings, files into MemPalace. Fires 23:00 nightly via systemd timer.
- **Weave** — Single function `capture_task()` that extracts + files any coding task output into MemPalace.
- **MemPalace bridge** — `recall()` and `capture()` functions work end-to-end.
- **CORAL grader** — Standalone experiment, 6/6 smoke test. Not integrated into daily workflow.

## What's NOT Working Yet

- **claw_task_runner.py** — Dead-end CLI tool. Not wired into agent workflows.
- **Code delivery** — Worktree changes aren't copied back to the real project.
- **Active recall** — Agents don't automatically query MemPalace before coding.
- **CORAL end-to-end** — Grader works standalone, not integrated into task pipeline.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Agent codes    │────▶│  weave.py    │────▶│  MemPalace  │
│  (any tool)     │     │  extract     │     │  storage    │
└─────────────────┘     └──────────────┘     └─────────────┘
                                │                    │
                                ▼                    ▼
                        ┌──────────────┐     ┌─────────────┐
                        │  E2B (:18081)│     │  recall()   │
                        │  or regex    │     │  for future │
                        └──────────────┘     └─────────────┘

┌─────────────────────────────────────────────┐
│  daily_capture.py (23:00 nightly)           │
│  Reads agent daily logs → Jess → MemPalace  │
└─────────────────────────────────────────────┘
```

## Dependencies

- Python 3.10+
- MemPalace CLI (in `~/.venvs/mempalace/bin/mempalace`)
- Gemma E2B on :18081 (for per-task extraction)
- Qwen 3.6 on :18080 (for daily capture)
