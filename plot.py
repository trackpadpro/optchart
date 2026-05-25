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
from typing import Any, Dict, List, Optional, Tuple


def import_plotting() -> tuple[Any, Any, Any]:
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "Matplotlib and numpy are required to generate the Gantt chart. "
            "Install them with `pip install matplotlib numpy`."
        ) from exc
    return mdates, plt, np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
POS_FILE = os.path.join(DATA_DIR, "positions.json")
TRACK_FILE = os.path.join(DATA_DIR, "tracking.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "gantt.png")


def parse_date(value: Any) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if not value:
        raise ValueError("Missing date value")

    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.datetime.strptime(value, fmt)
            except ValueError:
                continue
    raise ValueError(f"Unrecognized date format: {value}")


def load_positions() -> Dict[str, Any]:
    if not os.path.exists(POS_FILE):
        raise FileNotFoundError(f"Position file not found: {POS_FILE}. Run data.py first.")
    with open(POS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tracking() -> Dict[str, Any]:
    if not os.path.exists(TRACK_FILE):
        return {}
    with open(TRACK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def lookup_market_value(tracking_data: Dict[str, Any], symbol: str) -> Optional[float]:
    if not isinstance(tracking_data, dict):
        return None
    for entry in tracking_data.values():
        if not isinstance(entry, dict):
            continue
        options = entry.get("options")
        if isinstance(options, dict) and symbol in options:
            value = options[symbol].get("market_value")
            if isinstance(value, (int, float)):
                return value
    top_entry = tracking_data.get(symbol)
    if isinstance(top_entry, dict):
        value = top_entry.get("market_value")
        if isinstance(value, (int, float)):
            return value
    return None




def make_gantt_chart() -> None:
    if not os.path.exists(POS_FILE):
        print(f"No positions file found at {POS_FILE}; skipping Gantt chart.")
        return

    positions_data = load_positions()
    tracking_data = load_tracking()

    grouped_options: Dict[str, List[Dict[str, Any]]] = {}

    for entry in positions_data.get("summary", []):
        if not isinstance(entry, dict):
            continue

        instrument = entry.get("instrument") or {}
        symbol = entry.get("symbol") or instrument.get("symbol")
        underlying = instrument.get("underlyingSymbol") or entry.get("underlying_symbol") or "UNKNOWN"
        strike = entry.get("strike_price") or instrument.get("strikePrice")
        put_call = (instrument.get("putCall") or instrument.get("type") or "").upper()
        init_date = entry.get("init")
        expiration_date = entry.get("expiration_date")

        if not init_date or not expiration_date:
            continue

        try:
            start = parse_date(init_date)
            end = parse_date(expiration_date)
        except ValueError:
            continue

        duration = end - start
        if duration.total_seconds() <= 0:
            continue

        market_value = lookup_market_value(tracking_data, symbol) if symbol else None
        cost_basis = entry.get("cost_basis")
        bar_color = "lime" if isinstance(cost_basis, (int, float)) and isinstance(market_value, (int, float)) and market_value > cost_basis else "red"

        label_parts = [underlying, str(strike) if strike is not None else "", put_call]
        label = " ".join(part for part in label_parts if part).strip()
        if not label:
            label = symbol or "option"

        grouped_options.setdefault(underlying, []).append({
            "label": label,
            "start": start,
            "duration": duration,
            "bar_color": bar_color,
            "label_color": "green" if put_call == "CALL" else "red" if put_call == "PUT" else "white",
            "market_value": market_value if isinstance(market_value, (int, float)) else 0.0,
        })

    if not grouped_options:
        print("No valid option positions found for Gantt chart.")
        return

    ordered_underlyings = sorted(
        grouped_options.items(),
        key=lambda item: sum(opt["market_value"] for opt in item[1]),
        reverse=True,
    )

    rows: List[str] = []
    starts: List[datetime.datetime] = []
    durations: List[datetime.timedelta] = []
    colors: List[str] = []
    label_colors: List[str] = []

    for _, options in ordered_underlyings:
        for option in options:
            rows.append(option["label"])
            starts.append(option["start"])
            durations.append(option["duration"])
            colors.append(option["bar_color"])
            label_colors.append(option["label_color"])

    try:
        mdates, plt, np = import_plotting()
    except RuntimeError as exc:
        print(exc)
        return

    fig, ax = plt.subplots(figsize=(12, max(4, len(rows) * 0.5)))
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#252525")

    y_positions = np.arange(len(rows))[::-1] * 10
    for i in range(len(rows)):
        ax.broken_barh(
            [(mdates.date2num(starts[i]), durations[i].days)],
            (y_positions[i] - 2.5, 5),
            facecolors=colors[i],
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(rows)
    for tick, color in zip(ax.get_yticklabels(), label_colors):
        tick.set_color(color)

    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=45)

    ax.tick_params(colors="white", which="both")
    for spine in ax.spines.values():
        spine.set_color("white")

    ax.set_title("Option position Gantt chart", color="white")

    plt.tight_layout()
    os.makedirs(DATA_DIR, exist_ok=True)
    fig.savefig(OUTPUT_FILE, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    make_gantt_chart()
