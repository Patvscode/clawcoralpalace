import argparse
import os
import shutil
import subprocess
import tempfile
import yaml
from pathlib import Path

def run_task(task_config_path: str, scope_files: list[str], base_workdir: str):
    """
    Creates an isolated worktree, symlinks required files, and runs claw-code.
    """
    task_path = Path(task_config_path).resolve()
    if not task_path.exists():
        print(f"Error: Task config {task_config_path} not found.")
        return

    # Load task config
    with open(task_path, 'r') as f:
        config = yaml.safe_load(f)

    # Setup isolated workspace
    with tempfile.TemporaryDirectory(prefix="claw_task_") as tmp_dir:
        worktree = Path(tmp_dir) / "worktree"
        worktree.mkdir()
        
        print(f"🚀 Creating isolated workspace: {worktree}")

        # 1. Symlink the scope files (the 'Scrubber' part)
        for file_str in scope_files:
            src = Path(file_str).resolve()
            if src.exists():
                dest = worktree / src.name
                os.symlink(src, dest)
                print(f"  ✅ Linked: {src.name}")
            else:
                print(f"  ⚠️ Warning: {file_str} not found.")

        # 2. Symlink essential instruction files (The 'Durable' part)
        # We look for AGENTS.md or CLAUDE.md in the parent or current dir
        for instr_file in ["AGENTS.md", "CLAUDE.md", "CORAL.md"]:
            # Check current dir, then parent
            found = False
            for search_dir in [Path.cwd(), Path.cwd().parent]:
                candidate = search_dir / instr_file
                if candidate.exists():
                    os.symlink(candidate, worktree / instr_file)
                    print(f"  ✅ Linked Instruction: {instr_file}")
                    found = True
                    break
            if not found:
                print(f"  ℹ️ Note: No {instr_file} found to link.")

        # 3. Prepare Command
        # We use the model from config or default to gemma-4-26b
        model = config.get("model", "gemma-4-26b")
        claw_path = os.environ.get("CLAW_PATH", "/home/pmello/bin/claw-code")
        
        # Build the command (mimicking CORAL's pattern)
        cmd = [
            claw_path,
            "--model", model,
            "--permission-mode", "danger-full-access",
            "--output-format", "json",
            "prompt", "Execute the task defined in the provided files."
        ]

        print(f"🛠️ Running command: {' '.join(cmd)}")
        print(f"📂 Working Directory: {worktree}")

        # 4. Execute
        try:
            result = subprocess.run(
                cmd,
                cwd=str(worktree),
                capture_output=True,
                text=True,
                check=True
            )
            print("✨ Task completed successfully!")
            print("--- Output ---")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"❌ Task failed with exit code {e.returncode}")
            print("--- Error ---")
            print(e.stderr)
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claw Task Runner (The Scrubber)")
    parser.add_argument("config", help="Path to the task.yaml configuration file")
    parser.add_argument("--scope", nargs="+", help="List of files to include in the worktree", required=True)
    parser.add_argument("--workdir", default=".", help="Base directory for relative paths")

    args = parser.parse_args()
    run_task(args.config, args.scope, args.workdir)
