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

import compileall
import json
import os
import sys

root = os.path.dirname(os.path.abspath(__file__))

print("Compiling Python files for syntax check...")
ok = compileall.compile_dir(root, force=True, quiet=1)
if not ok:
    print("Compilation errors found.")
    sys.exit(2)

issues = False
auth_dir = os.path.join(root, "auth")
data_dir = os.path.join(root, "data")

def check_json(path: str) -> None:
    global issues
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
            print(f"OK JSON: {path}")
        except Exception as e:
            print(f"Invalid JSON: {path} {e}")
            issues = True


check_json(os.path.join(auth_dir, "client.json"))
check_json(os.path.join(auth_dir, "token.json"))
check_json(os.path.join(auth_dir, "token_response.json"))
check_json(os.path.join(data_dir, "positions.json"))
check_json(os.path.join(data_dir, "tracking.json"))

if issues:
    print("One or more JSON files are invalid.")
    sys.exit(3)

print("All checks passed.")
sys.exit(0)
