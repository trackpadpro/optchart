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

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

import auth

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
POS_FILE = os.path.join(DATA_DIR, "positions.json")
TRACK_FILE = os.path.join(DATA_DIR, "tracking.json")

MARKETDATA_API_BASE = "https://api.schwabapi.com/marketdata/v1"
TRADER_API_BASE = "https://api.schwabapi.com/trader/v1"


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def get_access_token() -> str:
    tokens = auth.load_tokens()
    if not tokens or "access_token" not in tokens:
        raise RuntimeError("No access token found. Run the initial handshake first.")
    return tokens["access_token"]


def is_option_position(pos: Dict[str, Any]) -> bool:
    instrument = pos.get("instrument") or {}
    if isinstance(instrument, dict) and instrument.get("assetType") == "OPTION":
        return True
    if pos.get("assetType") == "OPTION":
        return True
    # Flexible fallback: look for common fields containing 'option' or 'derivative'
    keys_to_check = [
        pos.get("securityType"),
        pos.get("assetType"),
        pos.get("type"),
        json.dumps(instrument).lower(),
    ]
    for v in keys_to_check:
        if not v:
            continue
        if isinstance(v, str) and ("option" in v.lower() or "derivative" in v.lower()):
            return True
        if isinstance(v, dict) and any("option" in str(x).lower() for x in v.values()):
            return True
    return False


def collect_position_info(position: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    instrument = position.get("instrument", {}) or {}

    # Common fields if present
    result["symbol"] = position.get("symbol") or instrument.get("symbol")
    quantity = position.get("quantity")
    if not isinstance(quantity, (int, float)):
        long_quantity = position.get("longQuantity") or position.get("quantityLong") or 0.0
        short_quantity = position.get("shortQuantity") or position.get("quantityShort") or 0.0
        quantity = float(long_quantity - short_quantity)
    result["quantity"] = quantity
    result["cost_basis"] = position.get("costBasis") or position.get("costBasisPerShare") or position.get("averageCost")
    result["instrument"] = instrument
    result["strike_price"] = instrument.get("strikePrice") or instrument.get("strike") or instrument.get("exercisePrice")
    result["expiration_date"] = instrument.get("expirationDate") or instrument.get("expiryDate") or instrument.get("expiration")
    result["underlying_symbol"] = instrument.get("underlyingSymbol") or instrument.get("underlying") or instrument.get("rootSymbol")

    # Lots (purchase history)
    lots: List[Dict[str, Any]] = []
    if "lots" in position and isinstance(position["lots"], list):
        for l in position["lots"]:
            lots.append({
                "quantity": l.get("quantity"),
                "lot_init": l.get("acquiredDate") or l.get("purchaseDate") or l.get("lotInit"),
                "cost_basis": l.get("costBasis") or l.get("costBasisPerShare") or l.get("price"),
            })
    result["lots"] = lots

    return result


def _extract_encrypted_account_id(account: Any) -> Optional[str]:
    """Extract the encrypted account ID from an account object. Prioritizes encrypted/hashed fields."""
    if not isinstance(account, dict):
        return None

    # Prioritize encrypted/hash fields over plaintext
    for key in (
        "hashValue",
        "accountNumberEncrypted",
        "accountNumberHash",
        "encryptedAccountNumber",
        "hashedAccountNumber",
        "hash",
        "encrypted",
    ):
        value = account.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_account_numbers(data: Any) -> List[Dict[str, Any]]:
    """Parse accountNumbers response, extracting encrypted account IDs only."""
    accounts: List[Dict[str, Any]] = []
    
    # Try direct accountNumbers array first
    if isinstance(data, dict) and "accountNumbers" in data and isinstance(data["accountNumbers"], list):
        for item in data["accountNumbers"]:
            if isinstance(item, dict):
                encrypted_id = _extract_encrypted_account_id(item)
                if encrypted_id:
                    account_record: Dict[str, Any] = {"account_id": encrypted_id}
                    if "accountNumber" in item:
                        account_record["account_number"] = item.get("accountNumber")
                    accounts.append(account_record)
        if accounts:
            return accounts
    
    # Try accounts array
    if isinstance(data, dict) and "accounts" in data and isinstance(data["accounts"], list):
        for item in data["accounts"]:
            if isinstance(item, dict):
                encrypted_id = _extract_encrypted_account_id(item)
                if encrypted_id:
                    account_record: Dict[str, Any] = {"account_id": encrypted_id}
                    if "accountNumber" in item:
                        account_record["account_number"] = item.get("accountNumber")
                    accounts.append(account_record)
        if accounts:
            return accounts
    
    # Try direct list
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                encrypted_id = _extract_encrypted_account_id(item)
                if encrypted_id:
                    account_record: Dict[str, Any] = {"account_id": encrypted_id}
                    if "accountNumber" in item:
                        account_record["account_number"] = item.get("accountNumber")
                    accounts.append(account_record)
    
    return accounts


def fetch_accounts(session: requests.Session) -> List[Dict[str, Any]]:
    url = f"{TRADER_API_BASE}/accounts/accountNumbers"
    try:
        resp = session.get(url)
        resp.raise_for_status()
    except Exception as exc:
        print(f"Error fetching accounts from Schwab API: {exc}")
        return []

    try:
        data = resp.json()
    except Exception as exc:
        print(f"Failed to decode account JSON from Schwab response: {exc}")
        return []

    # accounts successfully fetched

    if data is None:
        print("No accounts data available from Schwab API; returning empty list.")
        return []

    accounts = _parse_account_numbers(data)
    if accounts:
        return accounts

    if isinstance(data, dict) and "accounts" in data:
        return data["accounts"]
    if isinstance(data, list):
        return data
    # Fallback: wrap dict in list
    return [data]


def fetch_positions_for_account(session: requests.Session, account_id: str) -> List[Dict[str, Any]]:
    """Fetch positions for an account using the encrypted account ID."""
    url = f"{TRADER_API_BASE}/accounts/{account_id}?fields=positions"

    try:
        resp = session.get(url)
    except Exception as exc:
        print(f"Failed to request positions {url}: {exc}")
        return []

    if resp.status_code == 404:
        print(f"Positions endpoint not found: {url} (404)")
        return []

    try:
        resp.raise_for_status()
    except Exception as exc:
        print(f"Error fetching positions from {url}: {exc} - {getattr(resp, 'text', '')}")
        return []

    try:
        data = resp.json()
    except Exception as exc:
        print(f"Failed to decode JSON from {url}: {exc}")
        return []

    if isinstance(data, dict):
        if "positions" in data and isinstance(data["positions"], list):
            return data["positions"]
        if "securitiesAccount" in data and isinstance(data["securitiesAccount"], dict):
            sec_acc = data["securitiesAccount"]
            if "positions" in sec_acc and isinstance(sec_acc["positions"], list):
                return sec_acc["positions"]
            # Some responses wrap account in array
            if "positions" in sec_acc and isinstance(sec_acc["positions"], dict):
                return [sec_acc["positions"]]
    if isinstance(data, list):
        return data
    # Fallback
    return []


def _previous_weekday(reference: datetime.date) -> datetime.date:
    candidate = reference - datetime.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= datetime.timedelta(days=1)
    return candidate


def _most_recent_weekday(reference: datetime.date) -> datetime.date:
    if reference.weekday() == 5:
        return reference - datetime.timedelta(days=1)
    if reference.weekday() == 6:
        return reference - datetime.timedelta(days=2)
    return reference


def _parse_option_metadata(instrument: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"strike_price": None, "expiration_date": None}
    description = instrument.get("description") or ""
    if isinstance(description, str) and description:
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", description)
        strike_match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", description)
        if date_match:
            metadata["expiration_date"] = date_match.group(1)
        if strike_match:
            try:
                metadata["strike_price"] = float(strike_match.group(1))
            except ValueError:
                metadata["strike_price"] = None

    if metadata["expiration_date"] is None or metadata["strike_price"] is None:
        symbol = instrument.get("symbol") or ""
        symbol_match = re.search(r"(\d{6})([CP])([0-9]{8})$", symbol.replace(" ", ""))
        if symbol_match:
            if metadata["expiration_date"] is None:
                year = int(symbol_match.group(1)[:2]) + 2000
                month = int(symbol_match.group(1)[2:4])
                day = int(symbol_match.group(1)[4:6])
                metadata["expiration_date"] = f"{month:02d}/{day:02d}/{year}"
            if metadata["strike_price"] is None:
                raw_strike = symbol_match.group(3)
                try:
                    metadata["strike_price"] = float(int(raw_strike) / 1000)
                except ValueError:
                    metadata["strike_price"] = None

    return metadata


def run() -> None:
    ensure_data_dir()
    token = get_access_token()

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    accounts = fetch_accounts(session)
    existing_data = load_existing_positions()
    existing_summary: Dict[str, Dict[str, Any]] = {}
    for entry in existing_data.get("summary", []):
        if isinstance(entry, dict):
            symbol_key = _summary_symbol_key(entry)
            if symbol_key:
                existing_summary[symbol_key] = entry

    output: Dict[str, Any] = {"accounts": []}
    summary_by_symbol: Dict[str, Dict[str, Any]] = {}

    for acct in accounts:
        account_id = acct.get("account_id") if isinstance(acct, dict) else None
        if not account_id:
            continue

        try:
            positions = fetch_positions_for_account(session, account_id)
        except Exception as e:
            print(f"Failed to fetch positions for account {account_id}: {e}")
            continue

        option_positions = []
        for pos in positions:
            if not is_option_position(pos):
                continue

            long_quantity = pos.get("longQuantity") or 0
            short_quantity = pos.get("shortQuantity") or 0
            delta_quantity = long_quantity - short_quantity
            if delta_quantity == 0:
                continue

            option_positions.append(collect_position_info(pos))

            instrument = pos.get("instrument") or {}
            symbol = instrument.get("symbol") or pos.get("symbol")
            if not symbol:
                continue

            average_price = pos.get("averagePrice") or 0
            current_cost = pos.get("currentDayCost")

            if symbol not in summary_by_symbol:
                metadata = _parse_option_metadata(instrument)
                date_to_use = _most_recent_weekday(datetime.date.today()) if current_cost else _previous_weekday(datetime.date.today())
                init_value = None
                existing_entry = existing_summary.get(symbol)
                if isinstance(existing_entry, dict):
                    init_value = existing_entry.get("init")
                if not init_value:
                    init_value = date_to_use.strftime("%m/%d/%Y")

                summary_by_symbol[symbol] = {
                    "instrument": instrument,
                    "quantity": 0,
                    "cost_basis": 0.0,
                    "strike_price": metadata.get("strike_price"),
                    "expiration_date": metadata.get("expiration_date"),
                    "init": init_value,
                }

            summary_entry = summary_by_symbol[symbol]
            summary_entry["quantity"] += delta_quantity
            summary_entry["cost_basis"] += average_price * delta_quantity

            if summary_entry.get("strike_price") is None or summary_entry.get("expiration_date") is None:
                metadata = _parse_option_metadata(instrument)
                if summary_entry.get("strike_price") is None:
                    summary_entry["strike_price"] = metadata.get("strike_price")
                if summary_entry.get("expiration_date") is None:
                    summary_entry["expiration_date"] = metadata.get("expiration_date")

        output["accounts"].append({"account_id": account_id, "options": option_positions})

    output["summary"] = list(summary_by_symbol.values())

    existing_json = json.dumps(existing_data, sort_keys=True)
    new_json = json.dumps(output, sort_keys=True)
    if existing_data and existing_json == new_json:
        return

    with open(POS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)


def load_positions() -> Dict[str, Any]:
    if not os.path.exists(POS_FILE):
        raise FileNotFoundError(f"Position file not found: {POS_FILE}. Run data.py first.")
    with open(POS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_positions() -> Dict[str, Any]:
    if not os.path.exists(POS_FILE):
        return {}
    try:
        with open(POS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _summary_symbol_key(entry: Dict[str, Any]) -> Optional[str]:
    instr = entry.get("instrument") or {}
    if isinstance(instr, dict):
        return instr.get("symbol")
    return None


def fetch_quotes(session: requests.Session, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    if not symbols:
        return {}

    symbol_list = ",".join(symbols)
    url = f"{MARKETDATA_API_BASE}/quotes?symbols={symbol_list}"
    resp = session.get(url)
    if resp.status_code != 200:
        print(f"Unable to fetch quotes from Schwab API: {resp.status_code}")
        return {}

    data = resp.json()
    if isinstance(data, dict):
        if "quotes" in data and isinstance(data["quotes"], list):
            return {q["symbol"]: q for q in data["quotes"] if isinstance(q, dict) and isinstance(q.get("symbol"), str)}
        if "data" in data and isinstance(data["data"], list):
            return {q["symbol"]: q for q in data["data"] if isinstance(q, dict) and isinstance(q.get("symbol"), str)}
        if all(isinstance(v, dict) for v in data.values()):
            return {k: v for k, v in data.items() if isinstance(v, dict)}

    print("Unable to fetch quotes for symbols:", symbol_list)
    return {}


def fetch_earnings(session: requests.Session, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Attempt to fetch earnings info (including next earnings date) for symbols.
    Tries several likely Schwab API endpoints and returns a mapping symbol->info dict.
    If the API doesn't support earnings, returns empty dict.
    """
    if not symbols:
        return {}

    symbol_list = ",".join(symbols)
    url = f"{MARKETDATA_API_BASE}/earnings?symbols={symbol_list}"
    try:
        resp = session.get(url)
    except Exception as exc:
        print(f"Unable to fetch earnings from Schwab API: {exc}")
        return {}

    if resp.status_code != 200:
        print(f"Unable to fetch earnings from Schwab API: {resp.status_code}")
        return {}

    try:
        data = resp.json()
    except Exception as exc:
        print(f"Failed to decode earnings JSON from Schwab: {exc}")
        return {}

    if isinstance(data, dict):
        if "earnings" in data and isinstance(data["earnings"], list):
            earnings = {}
            for e in data["earnings"]:
                if isinstance(e, dict):
                    symbol = e.get("symbol")
                    if isinstance(symbol, str):
                        earnings[symbol] = e
            # earnings fetched
            return earnings
        if "data" in data and isinstance(data["data"], list):
            earnings = {}
            for e in data["data"]:
                if isinstance(e, dict):
                    symbol = e.get("symbol")
                    if isinstance(symbol, str):
                        earnings[symbol] = e
            # earnings fetched
            return earnings
        if all(isinstance(v, dict) for v in data.values()):
            # earnings fetched
            return {k: v for k, v in data.items() if isinstance(v, dict)}

    # No earnings data available from tried endpoints
    return {}


def update_tracking() -> None:
    ensure_data_dir()
    if not os.path.exists(POS_FILE):
        print(f"No positions file found at {POS_FILE}; skipping tracking update.")
        return

    token = get_access_token()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    positions_data = load_positions()

    # Collect option identifiers (symbol + cusip) and underlying symbols
    option_symbols: set = set()
    option_identifiers: set = set()
    all_underlying_symbols: set = set()

    for acct in positions_data.get("accounts", []):
        for entry in acct.get("options", []):
            instrument = entry.get("instrument") or {}
            symbol = entry.get("symbol") or instrument.get("symbol")
            cusip = instrument.get("cusip")
            if isinstance(symbol, str) and symbol:
                option_symbols.add(symbol)
                option_identifiers.add(symbol)
            if isinstance(cusip, str) and cusip:
                option_identifiers.add(cusip)
            underlying = instrument.get("underlyingSymbol")
            if isinstance(underlying, str) and underlying:
                all_underlying_symbols.add(underlying)

    # Fetch market data for all unique identifiers
    option_quotes = fetch_quotes(session, list(option_identifiers)) if option_identifiers else {}
    underlying_quotes = fetch_quotes(session, list(all_underlying_symbols)) if all_underlying_symbols else {}

    def _extract_mark(quote_data: Dict[str, Any]) -> Optional[float]:
        if not isinstance(quote_data, dict):
            return None
        for key in ("mark", "last", "lastPrice", "close"):
            value = quote_data.get(key)
            if isinstance(value, (int, float)):
                return value
        nested = quote_data.get("quote")
        if isinstance(nested, dict):
            for key in ("mark", "last", "lastPrice", "close"):
                value = nested.get(key)
                if isinstance(value, (int, float)):
                    return value
        nested = quote_data.get("extended")
        if isinstance(nested, dict):
            for key in ("mark", "last", "lastPrice", "close"):
                value = nested.get(key)
                if isinstance(value, (int, float)):
                    return value
        return None

    def _extract_last_earnings_date(quote_data: Dict[str, Any]) -> Optional[str]:
        if not isinstance(quote_data, dict):
            return None
        if isinstance(quote_data.get("lastEarningsDate"), str):
            return quote_data["lastEarningsDate"]
        fundamental = quote_data.get("fundamental")
        if isinstance(fundamental, dict):
            if isinstance(fundamental.get("lastEarningsDate"), str):
                return fundamental["lastEarningsDate"]
            if isinstance(fundamental.get("last_earnings_date"), str):
                return fundamental["last_earnings_date"]
        return None

    # Build tracking output with underlyings as top-level keys
    output: Dict[str, Any] = {}

    option_to_underlying: Dict[str, str] = {}
    option_quantities: Dict[str, float] = {}
    for acct in positions_data.get("accounts", []):
        for entry in acct.get("options", []):
            instrument = entry.get("instrument") or {}
            symbol = entry.get("symbol") or instrument.get("symbol")
            underlying = instrument.get("underlyingSymbol")
            if isinstance(symbol, str) and symbol:
                quantity = entry.get("quantity")
                if not isinstance(quantity, (int, float)):
                    long_quantity = entry.get("longQuantity") or entry.get("quantityLong") or 0.0
                    short_quantity = entry.get("shortQuantity") or entry.get("quantityShort") or 0.0
                    quantity = float(long_quantity - short_quantity)
                option_quantities[symbol] = option_quantities.get(symbol, 0.0) + float(quantity)
                if isinstance(underlying, str) and underlying:
                    option_to_underlying[symbol] = underlying

    for underlying_symbol in all_underlying_symbols:
        underlying_quote = underlying_quotes.get(underlying_symbol, {})
        output[underlying_symbol] = {
            "mark": _extract_mark(underlying_quote),
            "lastEarningsDate": _extract_last_earnings_date(underlying_quote),
            "next_earnings_date": None,
            "options": {},
        }

    for symbol in option_symbols:
        quote_data = option_quotes.get(symbol)
        if quote_data is None:
            for acct in positions_data.get("accounts", []):
                for entry in acct.get("options", []):
                    instrument = entry.get("instrument") or {}
                    if instrument.get("symbol") == symbol:
                        cusip = instrument.get("cusip")
                        if isinstance(cusip, str) and cusip:
                            quote_data = option_quotes.get(cusip)
                            if quote_data is not None:
                                break
                if quote_data is not None:
                    break
        mark_value = _extract_mark(quote_data or {})
        quantity = option_quantities.get(symbol, 0.0)
        market_value = None if mark_value is None else quantity * mark_value
        underlying_symbol = option_to_underlying.get(symbol)
        if underlying_symbol and underlying_symbol in output:
            output[underlying_symbol]["options"][symbol] = {
                "market_value": market_value,
            }
        else:
            output[symbol] = {
                "market_value": market_value,
                "options": {},
            }

    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch positions or update tracking data")
    parser.add_argument("--track", action="store_true", help="Generate data/tracking.json from data/positions.json")
    args = parser.parse_args()

    if args.track:
        update_tracking()
    else:
        run()
