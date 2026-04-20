# clawcoralpalace — Weave Plan

**Created:** 2026-04-20 19:02 EDT
**Status:** In progress — woven into OpenClaw, not a standalone tool
**Last updated:** 2026-04-20 19:02 EDT

---

## What Is This System?

clawcoralpalace is a knowledge-driven coding infrastructure layer for OpenClaw. It gives agents a better coding environment (isolated worktrees, recalled context from MemPalace) and a learning system that captures decisions, lessons, and patterns from every task — so smaller models can reuse the work of bigger models, and the system gets better over time.

**It should be woven into OpenClaw, not bolted on.** Agents should use it naturally through their normal workflow, not through a separate CLI tool.

---

## How It Should Work (End-to-End)

```
Agent receives coding task
    ↓
clawcoralpalace recalls relevant MemPalace knowledge (prior patterns, lessons, decisions)
    ↓
Agent codes in isolated worktree (via claw-code, clean environment)
    ↓
Worktree changes are copied back to the real project
    ↓
Compactor extracts structured knowledge from task output (decisions, lessons, patterns)
    ↓
Knowledge is filed into MemPalace for future recall
    ↓
CORAL (or internal grader) evaluates the outcome to track improvement over time
```

Every coding task flows through this pipeline. The agent doesn't need to know it's happening — it's the infrastructure under their feet.

---

## What We've Built (Phase-by-Phase)

### Phase 1: The Scrubber ✅
- `claw_task_runner.py` creates isolated worktrees with symlinked scope files
- Agents get a clean environment with only the files they need
- **Status:** Code exists but is a dead-end CLI tool. Not integrated into agent workflows.

### Phase 2: The Compactor ✅ (rewritten in Phase 5b)
- `compactor.py` extracts decisions, lessons, and code patterns from raw task output
- Files structured knowledge into MemPalace drawers
- **Current state:** Model-powered. Uses Gemma E2B on :18081 as primary extraction path. Falls back to regex on failure.
- **Tested:** E2B produces clean one-sentence extractions. Regex fallback verified by pointing at bogus URL.
- **Status:** Working but nobody feeds it data. The Compactor exists but has no input source in normal agent workflows.

### Phase 3: The Bridge ✅
- `mempalace_bridge.py` provides `recall()` and `capture()` functions
- Uses native `mempalace` CLI (not MCP) for reliable Python-to-Python calls
- `recall()` queries MemPalace for relevant prior knowledge before a task
- `capture()` files structured results back into MemPalace after a task
- **Status:** Working. Available for import by any module.

### Phase 4: Dashboard ✅
- `dashboard/` — web dashboard on port 8106 showing phase progress, task history
- Part of Clawboard hub at `hub/46-clawcoralpalace/`
- **Status:** Working but showing minimal data since no tasks flow through the pipeline.

### Phase 5a: Daily Autonomous Capture ✅
- `daily_capture.py` runs at 23:00 nightly
- Reads each agent's `memory/YYYY-MM-DD.md`
- Asks Jess (Qwen 35B on :18080) to extract structured learnings
- Files decisions, lessons, patterns, facts into MemPalace
- Fully autonomous, no human needed
- **Status:** Working. Timer is scheduled. This is the only piece actively producing knowledge right now.

### Phase 5b: Model-Powered Compaction ✅
- Replaced regex-based extraction in `compactor.py` with Gemma E2B
- Primary path: `http://localhost:18081/v1/chat/completions` (Gemma 4 E2B-it Q8_0)
- Fallback: regex pattern matching (verified by pointing at bogus URL)
- `ExtractionResult.method` reports which path ran ("e2b" or "regex")
- `use_model=False` flag lets tests force regex-only
- Env overrides: `E2B_URL`, `E2B_MODEL`, `E2B_TIMEOUT`
- **Status:** Working. Smoke-tested with sample YAML output.

### Phase 6a: CORAL Task + Grader ✅ (standalone experiment)
- `coral_task/` — a CORAL-runnable task that exercises the pipeline
- TaskGrader validates artifact quality (5 checks) + MemPalace integration (1 check)
- Grader tested: 6/6=1.0 with valid setup, 0/6=0.0 on negative
- **Status:** CORAL integration is a separate experiment. Not woven into OpenClaw.

---

## What We've Learned

### 1. The Compactor is the key piece
The knowledge extraction pipeline (compactor → MemPalace) is the thing that makes this system valuable. Everything else is scaffolding around it.

### 2. CORAL is not our runtime
CORAL (Human-Agent-Society/CORAL) is an external orchestration framework. It's not part of OpenClaw's daily operation. The CORAL integration is useful as a grading/evaluation layer — it validates that our pipeline produces measurable improvements — but it doesn't drive our tasks.

### 3. `claw_task_runner.py` is a dead-end
It's a manual CLI tool. Agents use claw-code directly. The runner creates worktrees but then throws the code away. It doesn't integrate into any agent workflow. **This is the biggest gap.**

### 4. Code delivery is missing
The worktree is a sandbox that deletes itself. Agent output is never copied back to the real project. The knowledge extraction works but has no consistent input source.

### 5. Daily capture is the only active piece
`daily_capture.py` running at 23:00 is the only thing actually producing knowledge right now. Everything else exists but isn't wired into anything.

### 6. Gemma E2B is the right compactor model
It's dedicated (port 18081), fast, always-on, and produces clean structured output. Better than Jess for this job because Jess is busy with daily capture and other tasks.

### 7. Fallback matters
The regex fallback in the Compactor is important. E2B can be unreachable, can return invalid JSON, can timeout. The system must never break because the model layer is down.

---

## Key Decisions

### Decision: Compactor uses Gemma E2B, not Jess
Jess handles daily capture (nightly). E2B handles per-task extraction (real-time). They serve different roles.

### Decision: CORAL as grading, not runtime
CORAL validates our pipeline quality. It doesn't run our tasks. This keeps OpenClaw's workflow simple and CORAL's role focused.

### Decision: System should be woven into OpenClaw, not separate
Agents shouldn't need to "use" clawcoralpalace. It should be the infrastructure under their feet. When an agent codes, knowledge is captured automatically. When a small model needs context, it's recalled automatically.

### Decision: CORAL integration is an experiment, not a dependency
The `coral_task/` directory exists as a standalone experiment. It's not imported by or integrated into any OpenClaw code. If CORAL changes or becomes irrelevant, we remove one directory and nothing else breaks.

---

## Current State Summary

| Component | Status | Active? | Notes |
|-----------|--------|---------|-------|
| Scrubber (worktrees) | Code exists | No | Dead-end CLI tool |
| Compactor | ✅ Working | No | Model-powered, but no input |
| Bridge (recall/capture) | ✅ Working | No | Available, not wired |
| Dashboard | ✅ Working | No | Minimal data |
| Daily capture | ✅ Working | **Yes** | Fires 23:00 nightly |
| CORAL grader | ✅ Working | No | Standalone experiment |

**Only daily capture is actively producing knowledge. Everything else is infrastructure waiting to be wired in.**

---

## What's Next

### Priority 1: Wire the Compactor into agent workflows
Agents need to feed their claw-code output into the Compactor. This doesn't mean wrapping every agent call — it means creating a hook or middleware that runs after claw-code execution and pipes the output through the Compactor.

Two approaches to evaluate:
1. **Claw-code wrapper** — intercept claw-code output before it returns to the agent
2. **Post-execution hook** — a script that watches for claw-code completion and feeds output to the Compactor

The Compactor needs data. The daily capture runs once a day. We need real-time extraction too.

### Priority 2: Fix code delivery
If claw_task_runner.py is going to exist, it should copy worktree changes back to the real project. But more importantly, agents using claw-code directly need a path to get their code into the project. This might be as simple as: "agent writes code → agent confirms → changes are applied." The worktree gives safety, the copy-back gives delivery.

### Priority 3: Make recall active in agent workflows
Agents should automatically query MemPalace for relevant context before coding. This is the Bridge's `recall()` function — but it needs to run automatically, not just when claw_task_runner.py is invoked.

### Priority 4: Close the loop — measure improvement
The CORAL grader (Phase 6a) proves we can grade outcomes. Phase 6b would be running CORAL evals and tracking scores over time. This is the "recursive self-improvement" signal — are we getting better at coding, and can we measure it?

### What NOT to build
- Don't make agents aware of clawcoralpalace. It's infrastructure, not a tool.
- Don't over-engineer the CORAL integration. It's a grading layer, not a runtime.
- Don't add more CLI tools. The goal is invisible integration, not more commands to run.

---

## File Map

| File | Purpose |
|------|---------|
| `claw_task_runner.py` | Task lifecycle engine (dead-end CLI — needs rework) |
| `compactor.py` | Knowledge extraction (Gemma E2B + regex fallback) — **key piece** |
| `mempalace_bridge.py` | MemPalace recall/capture functions |
| `daily_capture.py` | Nightly autonomous learning (23:00 timer) — only active piece |
| `coral_task/` | Standalone CORAL grading experiment |
| `dashboard/` | Web dashboard on port 8106 |
| `coral-daily-capture.service` | Systemd service for daily timer |
| `coral-daily-capture.timer` | Systemd timer (23:00 nightly) |

---

## Notes for Other Agents

If you're picking this up:

1. **Start with the Compactor.** It's the most valuable piece. Make sure it gets fed data from actual agent work.
2. **Don't touch CORAL unless asked.** It's an experiment. The `coral_task/` directory is standalone.
3. **The daily capture is working.** Don't break the timer. It fires at 23:00 EDT.
4. **Gemma E2B is on :18081.** That's the compactor model. Don't put other models there.
5. **Jess (Qwen 35B) is on :18080.** That's the daily capture model. Don't swap it.
6. **`mempalace` CLI** is at `~/.venvs/mempalace/bin/mempalace`. The bridge uses it for recall/capture.
7. **The goal is invisible integration.** Agents code with claw-code. Knowledge flows through MemPalace automatically. That's the win.

---

*This document lives in the GitHub repo so any agent can pick up context. Update it when the state changes.*
