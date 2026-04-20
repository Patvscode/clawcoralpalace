"""Phase 6a grader — CORAL TaskGrader for the end-to-end pipeline test.

Runs when CORAL executes the task:
  1. Checks that the agent produced a working utils.py (artifact quality)
  2. Verifies MemPalace has a drawer under our wing (pipeline integration)

Score = fraction of passing checks (0.0 – 1.0).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

from coral.config import GraderConfig
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle, Task


# ── MemPalace helper ──────────────────────────────────────────────

def _mempalace_bin() -> str | None:
    env = os.environ.get("MEMPALACE_BIN")
    if env:
        return env
    venv = Path.home() / ".venvs" / "mempalace" / "bin" / "mempalace"
    if venv.exists():
        return str(venv)
    return shutil.which("mempalace")


def _mempalace_has_wing(wing: str, timeout: int = 20) -> tuple[bool, str]:
    bin_path = _mempalace_bin()
    if not bin_path:
        return False, "mempalace CLI not found"

    for probe in ("phase6a", "safe_yaml_load", "yaml"):
        try:
            proc = subprocess.run(
                [bin_path, "search", "--wing", wing, "--results", "5", probe],
                capture_output=True, text=True, timeout=timeout,
            )
        except Exception:
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and out.strip() and "no" not in out.lower()[:40]:
            return True, f"search hit on probe `{probe}`"

    # Fallback: `status` lists everything filed.
    try:
        proc = subprocess.run(
            [bin_path, "status"], capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode == 0 and wing in (proc.stdout or ""):
            return True, "wing appears in `status`"
    except Exception:
        pass

    return False, "no CLI path located the wing"


# ── Artifact checks ───────────────────────────────────────────────

def _file_parses(path: Path) -> bool:
    try:
        ast.parse(path.read_text())
        return True
    except Exception:
        return False


def _defines_symbol(path: Path, name: str) -> bool:
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
    return False


def _runs_clean(path: Path, timeout: int = 15) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(path.parent),
        )
    except Exception as e:
        return False, f"spawn failed: {e}"
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}\nstderr:\n{proc.stderr[:500]}"
    return True, proc.stdout


# ── TaskGrader ────────────────────────────────────────────────────

class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        args = self.config.args or {}
        program_file = args.get("program_file", "utils.py")
        wing = args.get("wing", "clawcoralpalace-phase6a")
        codebase = Path(self.codebase_path)
        target = codebase / program_file

        checks: list[tuple[str, bool, str]] = []

        # A. Artifact quality
        exists = target.exists()
        checks.append(("file_exists", exists, str(target)))

        parses = exists and _file_parses(target)
        checks.append(("parses_as_python", parses, ""))

        defines_fn = parses and _defines_symbol(target, "safe_yaml_load")
        checks.append(("defines_safe_yaml_load", defines_fn, ""))

        runs_ok, run_output = (False, "")
        if defines_fn:
            runs_ok, run_output = _runs_clean(target)
        checks.append(("self_test_runs", runs_ok, run_output[:200]))

        mentions_pass = runs_ok and "PASS" in (run_output or "").upper()
        checks.append(("self_test_prints_pass", mentions_pass, ""))

        # B. Pipeline integration
        wing_found, wing_detail = _mempalace_has_wing(wing)
        checks.append(("mempalace_wing_filed", wing_found, wing_detail))

        total = len(checks)
        passed = sum(1 for _, ok, _ in checks if ok)
        score = passed / total if total else 0.0

        # Build explanation
        lines = ["Phase 6a evaluation"]
        for name, ok, detail in checks:
            lines.append(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))
        lines.append(f"\nScore: {passed}/{total} = {score:.3f}")

        return ScoreBundle(
            scores=[
                Score(
                    value=score,
                    name="phase6a_total",
                    explanation="\n".join(lines),
                )
            ],
            aggregated=score,
        )
