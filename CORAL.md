# CORAL.md — Orchestration Protocol

## What Is CORAL?
CORAL (Coordinated Orchestration, Retrieval, and Agent Lifecycle) is the intelligence layer
that manages how agents spawn, execute, learn, and persist knowledge across sessions.

## Core Principles
1. **Memory-first**: Before any task, query MemPalace for relevant prior work
2. **Isolated execution**: Every coding task runs in a scrubbed worktree (Phase 1)
3. **Knowledge capture**: Every completed task feeds results back into MemPalace
4. **Fail loud**: No silent fallbacks — if a model isn't available, stop and report

## Task Lifecycle
```
1. RECEIVE task definition
2. RECALL — query MemPalace for related knowledge (bridge.recall)
3. SCOPE — select only the files needed (Scrubber)
4. INJECT — write recalled context into worktree as CONTEXT.md
5. EXECUTE — run claw-code in the isolated worktree
6. CAPTURE — extract results, decisions, lessons → MemPalace (bridge.capture)
7. REPORT — summarize outcome to the requesting agent/user
```

## Agent Roles
| Agent | Role | Model |
|-------|------|-------|
| main | Orchestrator — plans, delegates, validates | claude-opus-4-7 |
| codex | Coding specialist — builds, debugs, ships | gpt-5.4 |
| q35 (Jess) | Local execution — fast, private, backup reasoning | qwen3.6-35b-a3b |
| gemma | Local multimodal — vision, generalist tasks | gemma-4-e4b |

## MemPalace Integration
- **Recall**: Before task execution, search MemPalace for:
  - Prior work on the same files/project (wing + room search)
  - Relevant lessons (search "lesson" + task keywords)
  - KG relationships for involved entities
- **Capture**: After task completion, file:
  - Decision rationale → `decisions` room
  - Code patterns learned → `code` room  
  - Failures/lessons → `lessons` room
  - KG facts for new entities/relationships

## Context Budget Rules
- Recalled context: max 2000 tokens injected as CONTEXT.md
- If recall returns >2000 tokens, summarize before injection
- Never inject raw MemPalace drawers — always curate relevance
