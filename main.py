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

import time

import auth
import data
import plot


def main() -> None:
    auth.ensure_auth_dir()
    auth.ensure_certs()
    tokens = auth.get_or_create_tokens()

    iteration = 0
    try:
        while True:
            # Check if token needs refreshing
            if auth.is_token_expired(tokens):
                tokens = auth.refresh_access_token(tokens)
            
            if iteration % 5 == 0:
                data.run()
            else:
                pass

            data.update_tracking()
            plot.make_gantt_chart()

            iteration += 1
            time.sleep(60)
    except KeyboardInterrupt:
        print("Stopped by user.")


if __name__ == "__main__":
    main()
