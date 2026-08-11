"""
Check that the single-instance guard blocks a second Vox process.

Run with: python tests/test_single_instance.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# The mutex only exists while its owner is alive, so the first process must
# still be running when the second one checks.
HOLD = (
    "import sys; sys.path.insert(0, {root!r}); from main import is_already_running; "
    "print(is_already_running(), flush=True); sys.stdin.readline()"
).format(root=str(ROOT))

CHECK = (
    "import sys; sys.path.insert(0, {root!r}); from main import is_already_running; "
    "print(is_already_running())"
).format(root=str(ROOT))


def main() -> int:
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        first = holder.stdout.readline().strip()
        assert first == "False", (
            f"first instance should be allowed, got {first!r} "
            "(is Vox.exe already running? close it and retry)"
        )

        second = subprocess.run(
            [sys.executable, "-c", CHECK], capture_output=True, text=True
        )
        assert second.stdout.strip() == "True", (
            f"second instance should be blocked, got {second.stdout!r} "
            f"{second.stderr!r}"
        )
    finally:
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=10)

    # The lock must be free again once the holder exits.
    after = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True)
    assert after.stdout.strip() == "False", f"lock not released, got {after.stdout!r}"

    print("OK: single-instance guard blocks the second process and releases on exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
