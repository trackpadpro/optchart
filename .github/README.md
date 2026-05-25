 # optchart — quick run guide

 This repository contains a minimal local tool to perform an OAuth handshake with the Schwab API, generate local TLS certs for the redirect server, and fetch option/derivative positions into a local JSON file.

 Files of interest
 - `auth/client.json` — stores your Schwab `client_id` and `client_secret` (created on first run)
 - `auth/token.json` — saved raw token response after the initial handshake
 - `auth/cert.pem`, `auth/key.pem` — local TLS certs used for the local redirect server
 - `data/positions.json` — output produced by `data.py` with option positions

 Quick start
 1. Install Python dependencies (if needed):
 ```bash
 python -m pip install requests cryptography
 ```

 2. Run the initial auth handshake to create client config and obtain tokens:
 ```bash
 python main.py
 ```
 On first run you will be prompted to paste your `Client ID` and `Client Secret` from the Schwab Developer Portal. These will be saved at `auth/client.json`.

 3. Fetch option positions (after successful auth):
 ```bash
 python data.py
 ```
 This writes `data/positions.json` with the structure: a list of accounts each containing `options` entries with `symbol`, `quantity`, `cost_basis`, and `lots` (each lot has `lot_init`, `quantity`, `cost_basis`).

 4. Populate tracking data from the saved positions:
 ```bash
 python data.py --track
 ```
 This writes `data/tracking.json` with current derivative price, strike price, and the current underlying asset price for each option/derivative position.

 5. Validate the project (syntax and JSON checks) without calling external APIs:
 ```bash
 python test.py
 ```

 Notes and tips
 - The project stores sensitive values locally (`auth/client.json` and `auth/token.json`). Do not commit these files to a public repository. Add an appropriate `.gitignore` before pushing.
 - If you want a requirements file, create `requirements.txt` with `requests` and `cryptography`.
