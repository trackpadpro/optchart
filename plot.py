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


def _format_money(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    try:
        rounded = round(float(v), 2)
        return f"${rounded:,.2f}"
    except Exception:
        return str(v)

FONT_FAMILY = "DejaVu Sans, Arial, sans-serif"
POSITIVE_COLOR = "#00ff00"
NEGATIVE_COLOR = "#ff0000"


def _format_money_html(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    try:
        value = float(v)
    except Exception:
        return str(v)

    rounded = round(value, 2)
    # If the value rounds to zero at two decimal places, show as $0.00
    if rounded == 0.0:
        return f"${abs(rounded):,.2f}"
    if rounded < 0:
        return f"(${abs(rounded):,.2f})"
    return f"${rounded:,.2f}"


def _money_color(v: Optional[float]) -> str:
    if v is None:
        return "white"
    try:
        value = float(v)
    except Exception:
        return "white"
    rounded = round(value, 2)
    # Values that round to $0.00 should be neutral/white
    if rounded == 0.0:
        return "white"
    if value < 0:
        return NEGATIVE_COLOR
    return POSITIVE_COLOR


def _compute_option_values(option: Dict[str, Any], tracking_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    underlying = option.get("underlying")
    strike = option.get("strike")
    put_call = option.get("put_call")
    quantity = option.get("quantity")
    market_value = option.get("market_value")
    underlying_mark = None

    if underlying and isinstance(tracking_data, dict) and underlying in tracking_data:
        try:
            underlying_mark = tracking_data[underlying].get("mark")
        except Exception:
            underlying_mark = None

    intrinsic_per = None
    if isinstance(underlying_mark, (int, float)) and isinstance(strike, (int, float)):
        if isinstance(put_call, str) and put_call.upper().startswith("C"):
            intrinsic_per = max(0.0, underlying_mark - float(strike))
        elif isinstance(put_call, str) and put_call.upper().startswith("P"):
            intrinsic_per = max(0.0, float(strike) - underlying_mark)

    premium_per = None
    if isinstance(market_value, (int, float)) and isinstance(quantity, (int, float)) and quantity != 0:
        premium_per = abs(market_value) / abs(quantity)

    sign = 1 if isinstance(quantity, (int, float)) and quantity >= 0 else -1
    intrinsic_total = None
    extrinsic_total = None
    if intrinsic_per is not None and isinstance(quantity, (int, float)):
        intrinsic_total = sign * intrinsic_per * abs(quantity)
    if intrinsic_per is not None and premium_per is not None and isinstance(quantity, (int, float)):
        extrinsic_total = sign * (premium_per - intrinsic_per) * abs(quantity)

    return {
        "intrinsic": intrinsic_total,
        "extrinsic": extrinsic_total,
    }


def _ordered_option_groups(positions_data: Dict[str, Any], tracking_data: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    grouped_options: Dict[str, List[Dict[str, Any]]] = {}

    for entry in positions_data.get("summary", []):
        if not isinstance(entry, dict):
            continue

        instrument = entry.get("instrument") or {}
        symbol = entry.get("symbol") or instrument.get("symbol")
        underlying = instrument.get("underlyingSymbol") or entry.get("underlying_symbol") or "UNKNOWN"
        strike = entry.get("strike_price") or instrument.get("strikePrice")
        put_call = (instrument.get("putCall") or entry.get("type") or "").upper()
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
        quantity = entry.get("quantity")
        if not isinstance(quantity, (int, float)):
            quantity = 0.0

        option_price = None
        if isinstance(market_value, (int, float)) and quantity != 0:
            try:
                option_price = abs(market_value) / abs(quantity)
            except Exception:
                option_price = market_value
        else:
            option_price = market_value if isinstance(market_value, (int, float)) else 0.0

        cost_basis = entry.get("cost_basis")
        bar_color = "lime" if isinstance(cost_basis, (int, float)) and isinstance(market_value, (int, float)) and market_value > cost_basis else "red"

        label_parts = [underlying, str(strike) if strike is not None else "", put_call]
        label = " ".join(part for part in label_parts if part).strip()
        if not label:
            label = symbol or "option"

        grouped_options.setdefault(underlying, []).append({
            "label": label,
            "symbol": symbol,
            "start": start,
            "duration": duration,
            "bar_color": bar_color,
            "cost_basis": cost_basis,
            "label_color": "green" if put_call == "CALL" else "red" if put_call == "PUT" else "white",
            "market_value": market_value if isinstance(market_value, (int, float)) else 0.0,
            "option_price": option_price,
            "quantity": quantity,
            "strike": strike,
            "put_call": put_call,
            "underlying": underlying,
        })

    for option_list in grouped_options.values():
        option_list.sort(key=lambda opt: opt.get("option_price") or 0.0, reverse=True)

    ordered_underlyings = sorted(
        grouped_options.items(),
        key=lambda item: sum(opt.get("market_value", 0.0) for opt in item[1]),
        reverse=True,
    )

    return ordered_underlyings


def _build_values_table_html(groups: List[Tuple[str, List[Dict[str, Any]]]]) -> str:
    html = [
        "<div style='width:100%; overflow-x:auto; margin-top:8px;'>",
        f"<table style='border-collapse:collapse; width:auto; min-width:540px; font-family: {FONT_FAMILY}; color:white; table-layout:auto;'>",
        "<thead>",
        "<tr>",
        "<th style='text-align:left; padding:8px; border:1px solid #2a2a2a; background:#121212; white-space:nowrap;'>Underlying</th>",
        "<th style='text-align:left; padding:8px; border:1px solid #2a2a2a; background:#121212; white-space:nowrap;'>Position</th>",
        "<th style='text-align:right; padding:8px; border:1px solid #2a2a2a; background:#121212; white-space:nowrap;'>Qty</th>",
        "<th style='text-align:right; padding:8px; border:1px solid #2a2a2a; background:#121212; white-space:nowrap;'>Intrinsic</th>",
        "<th style='text-align:right; padding:8px; border:1px solid #2a2a2a; background:#121212; white-space:nowrap;'>Extrinsic</th>",
        "</tr>",
        "</thead>",
        "<tbody>",
    ]
    tracking = load_tracking()

    for underlying, options in groups:
        n = len(options)
        # representative mark: use tracking mark for the underlying if available
        rep_mark = None
        try:
            entry = tracking.get(underlying) if isinstance(tracking, dict) else None
            if isinstance(entry, dict):
                rep_mark = entry.get("mark")
        except Exception:
            rep_mark = None

        underlying_label = underlying
        if rep_mark is not None:
            try:
                underlying_label = f"{underlying} {float(rep_mark):,.2f}"
            except Exception:
                underlying_label = f"{underlying} {rep_mark}"

        for idx, option in enumerate(options):
            values = _compute_option_values(option, tracking)
            intrinsic = values["intrinsic"]
            extrinsic = values["extrinsic"]
            intrinsic_html = _format_money_html(intrinsic)
            extrinsic_html = _format_money_html(extrinsic)
            intrinsic_color = _money_color(intrinsic)
            extrinsic_color = _money_color(extrinsic)
            if idx == 0:
                # Render underlying cell with rowspan equal to number of options
                # Position cell: prevent wrapping so PUT/CALL stays on same line
                html.append(
                    "<tr>"
                    "<td rowspan='%d' style='padding:8px; border:1px solid #2a2a2a; font-weight:bold; background:#262626; vertical-align:middle; white-space:nowrap;'>%s</td>"
                        "<td style='padding:8px; border:1px solid #2a2a2a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right; color:%s;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right; color:%s;'>%s</td>"
                    "</tr>" % (
                        n,
                        underlying_label,
                        option["label"],
                        option["quantity"],
                        intrinsic_color,
                        intrinsic_html,
                        extrinsic_color,
                        extrinsic_html,
                    )
                )
            else:
                html.append(
                    "<tr>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right; color:%s;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #2a2a2a; text-align:right; color:%s;'>%s</td>"
                    "</tr>" % (
                        option["label"],
                        option["quantity"],
                        intrinsic_color,
                        intrinsic_html,
                        extrinsic_color,
                        extrinsic_html,
                    )
                )
    html.append("</tbody></table></div>")
    return "".join(html)


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

    ordered_underlyings = _ordered_option_groups(positions_data, tracking_data)
    if not ordered_underlyings:
        print("No valid option positions found for Gantt chart.")
        return

    rows: List[str] = []
    starts: List[datetime.datetime] = []
    durations: List[datetime.timedelta] = []
    colors: List[Any] = []
    outline_colors: List[Optional[str]] = []
    label_colors: List[str] = []
    expiration_labels: List[str] = []

    for _, options in ordered_underlyings:
        for option in options:
            rows.append(option["label"])
            starts.append(option["start"])
            durations.append(option["duration"])
            # compute opacity from market_value and cost_basis: 1 - min(1, market_value/cost_basis)
            market_value = option.get("market_value")
            cost_basis = option.get("cost_basis")
            alpha = 1.0
            outline_color = None
            try:
                if isinstance(market_value, (int, float)) and isinstance(cost_basis, (int, float)) and cost_basis != 0:
                    ratio = market_value / cost_basis
                    alpha = 1.0 - min(1.0, ratio)
                    # Determine outline color for all bars
                    if isinstance(cost_basis, (int, float)) and isinstance(market_value, (int, float)) and cost_basis == market_value:
                        outline_color = "white"
                    else:
                        outline_color = POSITIVE_COLOR if option.get("bar_color") in ("lime", "green") else NEGATIVE_COLOR if option.get("bar_color") in ("red",) else "white"
            except Exception:
                alpha = 1.0
            # map base color to hex and convert to RGBA
            base_hex = POSITIVE_COLOR if option.get("bar_color") in ("lime", "green") else NEGATIVE_COLOR if option.get("bar_color") in ("red",) else "#ffffff"
            try:
                h = base_hex.lstrip("#")
                r = int(h[0:2], 16) / 255.0
                g = int(h[2:4], 16) / 255.0
                b = int(h[4:6], 16) / 255.0
                colors.append((r, g, b, max(0.0, min(1.0, alpha))))
            except Exception:
                colors.append(base_hex)
            outline_colors.append(outline_color)
            label_colors.append(option["label_color"])
            expiration_labels.append((option["start"] + option["duration"]).strftime("%m/%d/%Y"))

    try:
        mdates, plt, np = import_plotting()
    except RuntimeError as exc:
        print(exc)
        return

    fig, ax = plt.subplots(figsize=(9, max(6, len(rows) * 0.6)))
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#252525")
    plt.rcParams["font.family"] = "DejaVu Sans"

    y_positions = np.arange(len(rows))[::-1] * 13

    for i in range(len(rows)):
        ax.broken_barh(
            [(mdates.date2num(starts[i]), durations[i].days)],
            (y_positions[i] - 3, 6),
            facecolors=colors[i],
        )

    # Draw right-edge outlines for transparent bars
    for i in range(len(rows)):
        if outline_colors[i] is not None:
            x_right = mdates.date2num(starts[i]) + durations[i].days
            ax.plot(
                [x_right, x_right],
                [y_positions[i] - 3, y_positions[i] + 3],
                color=outline_colors[i],
                linewidth=1.5,
                solid_capstyle="butt",
            )

    # intrinsic/extrinsic labels are intentionally omitted from the Gantt chart

    ax.set_yticks(y_positions)
    ax.set_yticklabels(rows)
    for tick, color in zip(ax.get_yticklabels(), label_colors):
        tick.set_color(color)
        try:
            tick.set_fontsize(10)
        except Exception:
            pass

    x_max = max(mdates.date2num(starts[i] + durations[i]) for i in range(len(rows))) if rows else None
    if x_max is not None:
        current_xlim = ax.get_xlim()
        right_margin = max(2.5, (x_max - current_xlim[0]) * 0.04)
        ax.set_xlim(current_xlim[0], max(current_xlim[1], x_max + right_margin + 1.5))
        label_x = x_max + right_margin + 10.0
        for i, exp_label in enumerate(expiration_labels):
            ax.text(
                label_x,
                y_positions[i],
                exp_label,
                color="white",
                ha="left",
                va="center",
                fontsize=9,
            )

    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=45)

    ax.tick_params(colors="white", which="both", labelsize=10)
    for spine in ax.spines.values():
        spine.set_color("white")

    ax.set_title("Option position Gantt chart", color="white", fontsize=14)

    plt.tight_layout()
    os.makedirs(DATA_DIR, exist_ok=True)
    fig.savefig(OUTPUT_FILE, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    make_gantt_chart()


def streamlit_dashboard() -> None:
    try:
        import streamlit as st
    except Exception as exc:
        raise RuntimeError("Streamlit is required for the dashboard. Install with `pip install streamlit`.") from exc

    st.set_page_config(page_title="Options Dashboard", layout="wide")
    st.markdown(
        f"""
        <style>
        body, .stApp, .block-container {{ background-color: #1e1e1e; color: white; font-family: {FONT_FAMILY}; }}
        .stApp .css-1d391kg, .stApp .css-1d391kg * {{ color: white; }}
        .stButton>button {{ background-color: #333333; color: white; }}
        table {{ border-collapse: collapse; width:100%; font-size:13.5px; }}
        th, td {{ padding: 8px; border: 1px solid #2a2a2a; }}
        th {{ background: #121212; color: white; }}
        tr:nth-child(even) {{ background: #252525; }}
        tr:nth-child(odd) {{ background: #1e1e1e; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Options Dashboard")

    # Ensure chart exists (generate if needed)
    try:
        make_gantt_chart()
    except Exception:
        pass

    col1, col2 = st.columns([3, 1.65])

    with col1:
        if os.path.exists(OUTPUT_FILE):
            st.image(OUTPUT_FILE, width=700)
        else:
            st.info("No Gantt chart available. Run the position update to generate `gantt.png`.")

    positions = []
    try:
        positions_data = load_positions()
        tracking_data = load_tracking()
        positions = _ordered_option_groups(positions_data, tracking_data)
    except Exception:
        positions = []

    with col2:
        if positions:
            st.markdown(_build_values_table_html(positions), unsafe_allow_html=True)
        else:
            st.info("No position values available")
