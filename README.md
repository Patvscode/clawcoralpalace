# clawcoralpalace ⚡

The unified orchestration stack for the OpenClaw ecosystem.

## What It Does

`clawcoralpalace` integrates four layers into a single task lifecycle:

| Layer | Component | Role |
|-------|-----------|------|
| **Kernel** | OpenClaw | Hardware, model routing, agent comms |
| **Orchestrator** | CORAL | Task lifecycle, agent coordination |
| **Knowledge** | MemPalace | Long-term memory, RAG, knowledge graph |
| **Execution** | Claw Code | Isolated coding agent loops |

## Quick Start

```bash
# Run a task with full CORAL lifecycle
python claw_task_runner.py examples/fix-yaml-bug.yaml \
    --scope src/config.py tests/test_config.py

# Dry run (shows what would happen)
python claw_task_runner.py examples/fix-yaml-bug.yaml \
    --scope src/config.py --dry-run

# Skip MemPalace integration (just run the Scrubber)
python claw_task_runner.py examples/fix-yaml-bug.yaml \
    --scope src/config.py --skip-recall --skip-capture
```

## The CORAL Task Lifecycle

```
RECEIVE → RECALL → SCOPE → INJECT → EXECUTE → CAPTURE → REPORT
           ↑ MemPalace     ↑ Scrubber          ↑ Compactor
```

1. **RECEIVE** — Task definition (YAML/JSON config)
2. **RECALL** — Query MemPalace for prior knowledge about this work
3. **SCOPE** — Select only the files needed (the Scrubber)
4. **INJECT** — Write recalled context as CONTEXT.md in the worktree
5. **EXECUTE** — Run claw-code in the isolated worktree
6. **CAPTURE** — Extract decisions/lessons/patterns → file into MemPalace
7. **REPORT** — Summarize results back to the caller

## Architecture

### The Context Tiers

| Tier | Component | Function |
|------|-----------|----------|
| **Long-Term** | AGENTS.md, CORAL.md | Durable instructions, always present |
| **Mid-Term** | Compactor + MemPalace | Structured knowledge from past work |
| **Short-Term** | Scrubber worktrees | Only task-relevant files |

### Files

| File | Purpose |
|------|---------|
| `claw_task_runner.py` | Entry point — full CORAL lifecycle |
| `mempalace_bridge.py` | MemPalace integration (recall + capture) |
| `compactor.py` | Knowledge extraction from task output |
| `CORAL.md` | Orchestration protocol reference |
| `examples/` | Task config examples |
| `dashboard/` | Phase 4 web dashboard + API |

## Implementation Status

- [x] **Phase 1: The Scrubber** — Isolated worktree execution
- [x] **Phase 2: The Compactor** — Knowledge extraction + MemPalace filing
- [x] **Phase 3: The Bridge** — MemPalace recall → context injection (uses native `mempalace` CLI)
- [x] **Phase 4: Dashboard** — Clawboard hub page at `hub/46-clawcoralpalace/`, API on port 8106
- [x] **Phase 5a: Autonomous Daily Capture** — Jess (Qwen 35B) extracts learnings from daily logs, fires 23:00 nightly
- [x] **Phase 5b: Model-Powered Per-Task Compaction** — Gemma E2B (:18081) for real-time task compaction, regex fallback on failure
- [x] **Phase 6a: CORAL Task + Grader** — `coral_task/` holds a CORAL-runnable task + function grader that validates both artifact quality and MemPalace capture (6/6 on smoke test)
- [ ] **Phase 6b: CORAL End-to-End Run** — execute `coral start` against the task, confirm grader output + score propagation, add eval loop tests

## Task Config Format

```yaml
description: "What this task does"
model: "gemma-4-26b"           # Which model to use
wing: "myproject"              # MemPalace wing for filing
room: "code"                   # MemPalace room for filing
recall_query: "relevant search" # What to ask MemPalace before starting
entities: ["entity1"]          # KG entities to check
prompt: "Instructions for claw-code"
```

## Dependencies

- Python 3.10+
- `mcporter` CLI (for MemPalace MCP calls) or MemPalace HTTP endpoint
- `claw-code` binary (set `CLAW_PATH` env var if not at `/home/pmello/bin/claw-code`)
- Optional: `pyyaml` (for YAML configs; JSON always works)
