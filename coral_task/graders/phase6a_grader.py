"""
Phase 6a grader — verifies the end-to-end clawcoralpalace × CORAL loop.

Two families of checks:
  A. Artifact quality — did the agent produce a working utils.py?
  B. Pipeline integration — did our Compactor actually file knowledge
     into MemPalace under the expected wing?

Score is the fraction of passing checks (0.0 - 1.0).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path


# Same resolution strategy as mempalace_bridge.py — prefer venv, then PATH.
def _resolve_mempalace_bin() -> str | None:
    env = os.environ.get("MEMPALACE_BIN")
    if env:
        return env
    venv = Path.home() / ".venvs" / "mempalace" / "bin" / "mempalace"
    if venv.exists():
        return str(venv)
    return shutil.which("mempalace")


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
    """Execute the file as a script; must exit 0. stdout captured for pattern checks."""
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(path.parent),
        )
    except Exception as e:
        return False, f"spawn failed: {e}"
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}\nstderr:\n{proc.stderr[:500]}"
    return True, proc.stdout


def _mempalace_has_wing(wing: str, bin_path: str | None, timeout: int = 20) -> tuple[bool, str]:
    """Return (found, detail).

    Strategy: run `mempalace search --wing <wing> --results 5 <probe>` for a
    few generic probes. If the wing exists and has any drawer, results mention
    the wing or the probe term. Fallback: `mempalace status` should list wings.
    """
    if not bin_path:
        return False, "mempalace CLI not found"

    for probe in ("phase6a", "safe_yaml_load", "yaml"):
        args = [bin_path, "search", "--wing", wing, "--results", "5", probe]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except Exception:
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and out.strip() and "no" not in out.lower()[:40]:
            # Heuristic: non-empty output that isn't an explicit "no results" banner
            return True, f"search hit on probe `{probe}`"

    # Fallback: `status` lists everything that has been filed.
    try:
        proc = subprocess.run(
            [bin_path, "status"], capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode == 0 and wing in (proc.stdout or ""):
            return True, "wing appears in `status` output"
    except Exception:
        pass

    return False, "no CLI path located the wing"


def grade(codebase_path: str, tasks: list, **kwargs) -> float:
    """CORAL function-style grader entry point."""
    args = kwargs.get("args", {}) or {}
    program_file = args.get("program_file", "utils.py")
    wing = args.get("wing", "clawcoralpalace-phase6a")

    repo = Path(codebase_path)
    target = repo / program_file

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

    # B. Pipeline integration — did the Compactor file into MemPalace?
    bin_path = _resolve_mempalace_bin()
    wing_found, wing_detail = _mempalace_has_wing(wing, bin_path)
    checks.append(("mempalace_wing_filed", wing_found, wing_detail))

    # Score
    total = len(checks)
    passed = sum(1 for _, ok, _ in checks if ok)
    score = passed / total if total else 0.0

    # Human-readable log for the eval artifacts directory
    report = ["Phase 6a grader report", "=" * 40]
    for name, ok, detail in checks:
        report.append(f"[{'✓' if ok else '✗'}] {name}" + (f" — {detail}" if detail else ""))
    report.append("")
    report.append(f"Score: {passed}/{total} = {score:.3f}")
    print("\n".join(report))

    return score
