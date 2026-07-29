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
  4. Generating mode-specific Gantt chart visualizations (gantt_price.png and gantt_expiration.png)
"""

import compileall
import json
import os
import sys
from typing import List

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
    """Integration test: Verify chart images can be generated from existing data."""
    print("Testing Gantt chart generation...")
    data_dir = os.path.join(root, "data")
    pos_file = os.path.join(data_dir, "positions.json")
    price_file = os.path.join(data_dir, "gantt_price.png")
    expiration_file = os.path.join(data_dir, "gantt_expiration.png")

    if not os.path.exists(pos_file):
        print("  [INFO] Skipping Gantt test (no positions file)")
        return True

    for path in (price_file, expiration_file):
        if os.path.exists(path):
            os.remove(path)

    try:
        import plot

        plot.make_gantt_chart(output_file=price_file, sort_mode="market_value")
        plot.make_gantt_chart(output_file=expiration_file, sort_mode="expiration")

        if os.path.exists(price_file) and os.path.exists(expiration_file):
            size_price = os.path.getsize(price_file)
            size_expiration = os.path.getsize(expiration_file)
            print(f"  [OK] Gantt chart files generated successfully ({size_price} bytes, {size_expiration} bytes)")
            return True
        else:
            print("  [FAILED] One or more Gantt chart files were not created")
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
    results.append(check_expiration_sorting())
    print()
    results.append(check_expiration_mode_flat_ordering())
    print()
    results.append(check_expiration_mode_interleaves_underlyings())
    print()
    results.append(check_price_sorting())
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


def check_expiration_sorting() -> bool:
    """Verify expiration-based sorting uses expiration first and price only as a tie-breaker."""
    print("Checking expiration ordering...")
    try:
        import plot

        positions_data = {
            "summary": [
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL240119C00100000"},
                    "symbol": "AAPL240119C00100000",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-19",
                    "quantity": 1,
                    "cost_basis": 5,
                },
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL240126C00100000"},
                    "symbol": "AAPL240126C00100000",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-26",
                    "quantity": 1,
                    "cost_basis": 6,
                },
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL240126C00200000"},
                    "symbol": "AAPL240126C00200000",
                    "strike_price": 200,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-26",
                    "quantity": 1,
                    "cost_basis": 7,
                },
            ]
        }
        tracking_data = {}
        ordered = plot._ordered_options_for_chart(positions_data, tracking_data, sort_mode="expiration")
        expirations = [opt["expiration"] for opt in ordered]
        if expirations != sorted(expirations):
            print("  [FAILED] Expiration ordering did not sort by expiration date")
            return False

        first_same_expiration = [opt["label"] for opt in ordered if opt["expiration"] == expirations[2]]
        if first_same_expiration[0] != "AAPL 200 CALL":
            print("  [FAILED] Same-expiration tie-breaker did not prefer the higher-priced option")
            return False

        print("  [OK] Expiration ordering behaves as expected")
        return True
    except Exception as e:
        print(f"  [FAILED] Error checking expiration sorting: {e}")
        return False


def check_expiration_mode_flat_ordering() -> bool:
    """Verify expiration mode stays globally sorted by expiration rather than grouping by underlying."""
    print("Checking flat expiration ordering...")
    try:
        import plot

        positions_data = {
            "summary": [
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL-1"},
                    "symbol": "AAPL-1",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-19",
                    "quantity": 1,
                    "cost_basis": 5,
                },
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL-2"},
                    "symbol": "AAPL-2",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-21",
                    "quantity": 1,
                    "cost_basis": 6,
                },
                {
                    "instrument": {"underlyingSymbol": "TSLA", "putCall": "CALL", "symbol": "TSLA-1"},
                    "symbol": "TSLA-1",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-20",
                    "quantity": 1,
                    "cost_basis": 7,
                },
            ]
        }
        tracking_data = {}
        ordered = plot._ordered_options_for_chart(positions_data, tracking_data, sort_mode="expiration")
        labels = [opt["label"] for opt in ordered]
        expected = ["AAPL 100 CALL", "TSLA 100 CALL", "AAPL 100 CALL"]
        if labels != expected:
            print(f"  [FAILED] Expiration ordering should remain globally sorted: expected {expected}, got {labels}")
            return False

        print("  [OK] Expiration mode remains globally sorted")
        return True
    except Exception as e:
        print(f"  [FAILED] Error checking flat expiration ordering: {e}")
        return False


def check_expiration_mode_interleaves_underlyings() -> bool:
    """Verify expiration mode uses expiration dates as the primary sort even when multiple underlying groups are mixed together."""
    print("Checking mixed-underlying expiration ordering...")
    try:
        import plot

        positions_data = {
            "summary": [
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL-1"},
                    "symbol": "AAPL-1",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-21",
                    "quantity": 1,
                    "cost_basis": 5,
                },
                {
                    "instrument": {"underlyingSymbol": "PESI", "putCall": "CALL", "symbol": "PESI-1"},
                    "symbol": "PESI-1",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-20",
                    "quantity": 1,
                    "cost_basis": 7,
                },
                {
                    "instrument": {"underlyingSymbol": "AAPL", "putCall": "CALL", "symbol": "AAPL-2"},
                    "symbol": "AAPL-2",
                    "strike_price": 200,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-19",
                    "quantity": 1,
                    "cost_basis": 8,
                },
            ]
        }
        tracking_data = {}
        ordered = plot._ordered_options_for_chart(positions_data, tracking_data, sort_mode="expiration")
        expirations = [opt["expiration"] for opt in ordered]
        labels = [opt["label"] for opt in ordered]

        if expirations != sorted(expirations):
            print("  [FAILED] Expiration ordering did not prioritize expiration dates across mixed underlyings")
            return False

        expected_labels = ["AAPL 200 CALL", "PESI 100 CALL", "AAPL 100 CALL"]
        if labels != expected_labels:
            print(f"  [FAILED] Expiration ordering should place earlier expirations first across underlyings: expected {expected_labels}, got {labels}")
            return False

        print("  [OK] Mixed-underlying expiration ordering behaves as expected")
        return True
    except Exception as e:
        print(f"  [FAILED] Error checking mixed-underlying expiration ordering: {e}")
        return False


def check_price_sorting() -> bool:
    """Verify price-mode ordering puts longs ahead of shorts and keeps higher prices first."""
    print("Checking price ordering...")
    try:
        import plot

        positions_data = {
            "summary": [
                {
                    "instrument": {"underlyingSymbol": "PESI", "putCall": "CALL", "symbol": "PESI-LONG"},
                    "symbol": "PESI-LONG",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-19",
                    "quantity": 1,
                    "cost_basis": 5,
                },
                {
                    "instrument": {"underlyingSymbol": "PESI", "putCall": "PUT", "symbol": "PESI-SHORT"},
                    "symbol": "PESI-SHORT",
                    "strike_price": 100,
                    "init": "2024-01-01",
                    "expiration_date": "2024-01-19",
                    "quantity": -1,
                    "cost_basis": 5,
                },
            ]
        }
        tracking_data = {
            "PESI-LONG": {"market_value": 10},
            "PESI-SHORT": {"market_value": -50},
        }
        ordered = plot._ordered_options_for_chart(positions_data, tracking_data, sort_mode="market_value")
        if [opt["label"] for opt in ordered[:2]] != ["PESI 100 CALL", "PESI 100 PUT"]:
            print("  [FAILED] Price ordering did not place long positions ahead of short ones")
            return False

        print("  [OK] Price ordering behaves as expected")
        return True
    except Exception as e:
        print(f"  [FAILED] Error checking price sorting: {e}")
        return False


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
