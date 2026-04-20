# clawcoralpalace ⚡

The unified orchestration stack for the OpenClaw ecosystem.

`clawcoralpalace` integrates:
- **OpenClaw** (The Kernel): System management, model routing, and core tool access.
- **CORAL** (The Orchestrator): Multi-agent coordination, experiment loops, and task lifecycle management.
- **MemPalace** (The Knowledge Base): Distributed, structured long-term memory and RAG.
- **Claw Code** (The Execution Engine): High-performance, context-aware coding agents.

## 🏗️ Architecture

This repository contains the "glue" that makes these components work as a single, recursive, self-improving operating system.

### Core Components

| Component | Role | Implementation |
| :--- | :--- | :--- |
| **Context Scrubber** | Man/age context window via task-specific worktrees. | `claw-task-runner.py` |
| **Compactor** | Summarizes agent history and tool outputs. | `context-compactor/` |
| **Integration Hooks** | Connects CORAL lifecycles to OpenClaw traces. | `hooks/` |
| **Knowledge Sync** | Bridges MemPalace insights into agent prompts. | `mem-bridge/` |

## 🚀 Getting Started

*(Work in progress)*

## 🛠️ Development

*(Work in progress)*
