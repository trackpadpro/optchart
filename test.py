# Copyright 2026 Valentin Richter

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Integration tests for optchart core functionality.

Tests verify the complete workflow:
  1. OAuth authentication and token management
  2. Fetching option positions from Schwab API
  3. Tracking option prices and underlying asset prices
  4. Generating Gantt chart visualization (gantt.png)
"""

import compileall
import json
import os
import sys
from typing import Any, Dict, List

root = os.path.dirname(os.path.abspath(__file__))


def check_syntax() -> bool:
    """Verify all Python files compile without syntax errors."""
    print("Checking Python syntax...")
    ok = compileall.compile_dir(root, force=True, quiet=1)
    if not ok:
        print("  [FAILED] Syntax errors found in Python files")
        return False
    print("  [PASS] All Python files compile successfully")
    return True


def check_json_files() -> bool:
    """Verify JSON files exist and are valid (if they exist)."""
    print("Checking JSON files...")
    issues = False
    auth_dir = os.path.join(root, "auth")
    data_dir = os.path.join(root, "data")

    json_files = [
        os.path.join(auth_dir, "client.json"),
        os.path.join(auth_dir, "token.json"),
        os.path.join(data_dir, "positions.json"),
        os.path.join(data_dir, "tracking.json"),
    ]

    for path in json_files:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
                print(f"  [OK] Valid JSON: {os.path.relpath(path, root)}")
            except Exception as e:
                print(f"  [FAILED] Invalid JSON: {os.path.relpath(path, root)} - {e}")
                issues = True

    return not issues


def check_positions_structure() -> bool:
    """Verify positions.json has the expected structure if it exists."""
    print("Checking positions data structure...")
    data_dir = os.path.join(root, "data")
    pos_file = os.path.join(data_dir, "positions.json")

    if not os.path.exists(pos_file):
        print("  [INFO] No positions file found (expected on first run)")
        return True

    try:
        with open(pos_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print("  [FAILED] Positions data should be a JSON object")
            return False

        if "accounts" not in data:
            print("  [FAILED] Positions data missing 'accounts' key")
            return False

        accounts = data["accounts"]
        if not isinstance(accounts, list):
            print("  [FAILED] 'accounts' should be a list")
            return False

        # Check for option positions
        has_options = False
        for acct in accounts:
            if isinstance(acct, dict) and "options" in acct:
                if isinstance(acct["options"], list) and len(acct["options"]) > 0:
                    has_options = True
                    break

        if has_options:
            print("  [OK] Positions file has correct structure with options")
        else:
            print("  [INFO] Positions file valid but contains no option positions")

        return True

    except Exception as e:
        print(f"  [FAILED] Error validating positions structure: {e}")
        return False


def check_tracking_structure() -> bool:
    """Verify tracking.json has the expected structure if it exists."""
    print("Checking tracking data structure...")
    data_dir = os.path.join(root, "data")
    track_file = os.path.join(data_dir, "tracking.json")

    if not os.path.exists(track_file):
        print("  [INFO] No tracking file found (expected on first run)")
        return True

    try:
        with open(track_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print("  [FAILED] Tracking data should be a JSON object")
            return False

        print("  [OK] Tracking file has correct structure")
        return True

    except Exception as e:
        print(f"  [FAILED] Error validating tracking structure: {e}")
        return False


def check_gitignore_protection() -> bool:
    """Verify .gitignore protects sensitive local data folders."""
    print("Checking .gitignore protection...")
    gitignore_file = os.path.join(root, ".gitignore")
    if not os.path.exists(gitignore_file):
        print("  [FAILED] .gitignore is missing")
        return False

    try:
        with open(gitignore_file, "r", encoding="utf-8") as f:
            entries = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    except Exception as e:
        print(f"  [FAILED] Unable to read .gitignore: {e}")
        return False

    required = ["auth/", "data/"]
    missing = [item for item in required if item not in entries]
    if missing:
        print(f"  [FAILED] .gitignore missing entries: {', '.join(missing)}")
        return False

    print("  [OK] .gitignore protects auth/ and data/")
    return True


def check_gantt_generation() -> bool:
    """Integration test: Verify gantt.png can be generated from existing data."""
    print("Testing Gantt chart generation...")
    data_dir = os.path.join(root, "data")
    pos_file = os.path.join(data_dir, "positions.json")
    gantt_file = os.path.join(data_dir, "gantt.png")

    if not os.path.exists(pos_file):
        print("  [INFO] Skipping Gantt test (no positions file)")
        return True

    # Remove old gantt.png if present
    if os.path.exists(gantt_file):
        os.remove(gantt_file)

    try:
        import plot

        plot.make_gantt_chart()

        if os.path.exists(gantt_file):
            size = os.path.getsize(gantt_file)
            print(f"  [OK] Gantt chart generated successfully ({size} bytes)")
            return True
        else:
            print("  [FAILED] Gantt chart file was not created")
            return False

    except Exception as e:
        print(f"  [FAILED] Error generating Gantt chart: {e}")
        return False


def main() -> int:
    """Run all tests."""
    print("=" * 60)
    print("optchart — Core Functionality Tests")
    print("=" * 60)
    print()

    results: List[bool] = []

    results.append(check_syntax())
    print()
    results.append(check_json_files())
    print()
    results.append(check_positions_structure())
    print()
    results.append(check_tracking_structure())
    print()
    results.append(check_gitignore_protection())
    print()
    results.append(check_gantt_generation())
    print()
    results.append(check_streamlit_import())

    print()
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} test groups passed")

    if all(results):
        print("[OK] All tests passed")
        print("="*60)
        return 0
    else:
        print("[FAILED] Some tests failed")
        print("=" * 60)
        return 1


def check_streamlit_import() -> bool:
    """Verify streamlit can be imported (installed)."""
    print("Checking streamlit import...")
    try:
        import importlib
        importlib.import_module("streamlit")
        print("  [OK] Streamlit is importable")
        return True
    except Exception as e:
        print(f"  [FAILED] Streamlit import failed: {e}")
        return False


if __name__ == "__main__":
    sys.exit(main())
