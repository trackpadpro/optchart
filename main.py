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

import subprocess
import sys
import time

import auth
import data
import plot


def main() -> None:
    auth.ensure_auth_dir()
    auth.ensure_certs()
    tokens = auth.get_or_create_tokens()

    iteration = 0
    streamlit_process = None
    
    try:
        while True:
            # Check if token needs refreshing
            if auth.is_token_expired(tokens):
                try:
                    tokens = auth.refresh_access_token(tokens)
                except Exception as exc:
                    print(f"Token refresh failed: {exc}")
                    print("Attempting full authentication flow...")
                    tokens = auth.perform_initial_handshake()
            
            if iteration % 5 == 0:
                data.run()
            else:
                pass

            data.update_tracking()
            plot.make_gantt_chart()

            # Launch Streamlit dashboard after first iteration
            if iteration == 0:
                print("Launching Streamlit dashboard (dash.py)...")
                try:
                    streamlit_process = subprocess.Popen(
                        [sys.executable, "-m", "streamlit", "run", "dash.py", "--logger.level=warning"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print("Dashboard running at http://localhost:8501")
                except Exception as exc:
                    print(f"Failed to launch Streamlit: {exc}")

            iteration += 1
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        if streamlit_process:
            print("Shutting down Streamlit dashboard...")
            streamlit_process.terminate()
            try:
                streamlit_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                streamlit_process.kill()


if __name__ == "__main__":
    main()
