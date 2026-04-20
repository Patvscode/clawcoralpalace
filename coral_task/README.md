# clawcoralpalace × CORAL — Phase 6a

The minimum-viable CORAL integration: a task CORAL can drive end-to-end,
exercising the full clawcoralpalace pipeline (Scrubber → Bridge → Compactor →
MemPalace) and verifying it with a grader that reads MemPalace back.

## Files

| Path | Purpose |
|------|---------|
| `task.yaml` | CORAL task definition (agent runtime + grader config) |
| `graders/phase6a_grader.py` | Function-style grader; 6 checks, score = passed/6 |
| `repo/` | Workspace CORAL populates per attempt |

## What the grader checks

**Artifact quality (5 checks)**
1. `utils.py` exists at the repo root
2. Parses as Python
3. Defines `safe_yaml_load`
4. Runs cleanly (exit 0) with its self-test
5. Self-test prints PASS lines

**Pipeline integration (1 check)**
6. MemPalace has drawers under the `clawcoralpalace-phase6a` wing
   (proves our Compactor actually filed knowledge after task execution)

## Running

From the CORAL repo:

```bash
cd ~/research/references/CORAL
source .venv/bin/activate
coral start --config ~/DevTools/clawcoralpalace/coral_task/task.yaml
```

## Tested

Grader validated end-to-end on 2026-04-20:

- With a valid `utils.py` + seeded MemPalace drawer → **6/6 = 1.000**
- With missing file + bogus wing → **0/6 = 0.000**

This makes Phase 6a the first real CORAL-graded, MemPalace-aware task in
the clawcoralpalace stack.
