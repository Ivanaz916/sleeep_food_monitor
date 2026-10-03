import base64
import calendar
import io
import os
from datetime import date, datetime, time

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Sleep & Food Monitor", layout="wide")

# On stlite, /mnt is an IndexedDB-backed dir that persists in the browser
DATA_DIR = "/mnt" if os.path.isdir("/mnt") else os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(DATA_DIR, "entries.csv")

COLUMNS = [
    "date",
    "child",
    "morning_mood",
    "dinner_completeness",
    "night_wakings",
    "bedtime",
    "sleep_score",
    "timestamp",
]

# Bedtime -> sleep score mapping (times are PM)
BEDTIME_MAPPING = [
    {"bedtime_range": "8:00 PM - 8:45 PM", "sleep_score": 10},
    {"bedtime_range": "8:45 PM - 9:00 PM", "sleep_score": 8},
    {"bedtime_range": "9:00 PM - 9:15 PM", "sleep_score": 7},
    {"bedtime_range": "9:15 PM - 9:30 PM", "sleep_score": 6},
    {"bedtime_range": "9:30 PM or later", "sleep_score": 5},
]

DEFAULTS = {"mood": 10, "dinner": 10, "wakings": 0, "bedtime": time(20, 30)}


def bedtime_to_score(t):
    minutes = t.hour * 60 + t.minute
    if minutes < 20 * 60 + 45:
        return 10
    if minutes < 21 * 60:
        return 8
    if minutes < 21 * 60 + 15:
        return 7
    if minutes < 21 * 60 + 30:
        return 6
    return 5


def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE, dtype={"date": str, "bedtime": str})
    return pd.DataFrame(columns=COLUMNS)


def save_data(df):
    df.to_csv(DATA_FILE, index=False)


df = load_data()
dates_with_entries = set(df["date"]) if not df.empty else set()

today = date.today()
if "cal_year" not in st.session_state:
    st.session_state.cal_year = today.year
    st.session_state.cal_month = today.month
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today.isoformat()

st.title("Sleep & Food Monitor")

# ---- Calendar ----
nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
if nav_prev.button("<", use_container_width=True):
    st.session_state.cal_month -= 1
    if st.session_state.cal_month == 0:
        st.session_state.cal_month = 12
        st.session_state.cal_year -= 1
    st.rerun()
if nav_next.button(">", use_container_width=True):
    st.session_state.cal_month += 1
    if st.session_state.cal_month == 13:
        st.session_state.cal_month = 1
        st.session_state.cal_year += 1
    st.rerun()

year, month = st.session_state.cal_year, st.session_state.cal_month
nav_label.markdown(
    f"<h4 style='text-align:center'>{calendar.month_name[month]} {year}</h4>",
    unsafe_allow_html=True,
)

day_header = st.columns(7)
for col, name in zip(day_header, ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
    col.markdown(f"**{name}**")

cal = calendar.Calendar(firstweekday=6)
for week in cal.monthdayscalendar(year, month):
    cols = st.columns(7)
    for col, day in zip(cols, week):
        if day == 0:
            continue
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        has_entry = iso in dates_with_entries
        is_selected = iso == st.session_state.selected_date
        label = f"{day}" + (" *" if has_entry else "")
        if col.button(
            label,
            key=f"day-{iso}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            st.session_state.selected_date = iso
            st.rerun()

st.caption("Click a date to add or edit an entry. * = has saved entry.")

# ---- Entry form ----
sel = st.session_state.selected_date
st.subheader(f"Entry for {sel}")

child = st.selectbox("Child", ["NR", "MR"], key="child-select")

saved = df[(df["date"] == sel) & (df["child"] == child)]
if not saved.empty:
    row = saved.iloc[0]
    h, m = map(int, str(row["bedtime"]).split(":"))
    init = {
        "mood": int(row["morning_mood"]),
        "dinner": int(row["dinner_completeness"]),
        "wakings": int(row["night_wakings"]),
        "bedtime": time(h, m),
    }
else:
    init = DEFAULTS

# Keys include date+child so fields reload when the selection changes
k = f"{sel}-{child}"
dinner = st.slider("Dinner completeness (1-10, 10 = highly complete)", 1, 10,
                   init["dinner"], key=f"dinner-{k}")
wakings = st.number_input("Night wakings", min_value=0, step=1,
                          value=init["wakings"], key=f"wakings-{k}")
bedtime = st.time_input("Bedtime", value=init["bedtime"], key=f"bedtime-{k}")
mood = st.slider("Following Morning mood (1-10, 10 = great mood)", 1, 10,
                 init["mood"], key=f"mood-{k}")

btn_save, btn_clear, _ = st.columns([1, 1, 3])
if btn_save.button("Save", type="primary", use_container_width=True):
    df = df[~((df["date"] == sel) & (df["child"] == child))]
    new_row = {
        "date": sel,
        "child": child,
        "morning_mood": mood,
        "dinner_completeness": dinner,
        "night_wakings": int(wakings),
        "bedtime": bedtime.strftime("%H:%M"),
        "sleep_score": bedtime_to_score(bedtime),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values(["date", "child"])
    save_data(df)
    st.rerun()

if btn_clear.button("Clear saved entry", use_container_width=True):
    df = df[~((df["date"] == sel) & (df["child"] == child))]
    save_data(df)
    st.rerun()

# ---- Plots ----
st.divider()


def build_plot_df(df):
    """Join each day's mood with the prior day's dinner/sleep per child."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    prior = d[["date", "child", "dinner_completeness", "sleep_score"]].copy()
    prior["date"] = prior["date"] + pd.Timedelta(days=1)
    prior = prior.rename(columns={
        "dinner_completeness": "prior_day_eating",
        "sleep_score": "prior_night_sleep_score",
    })
    return d[["date", "child", "morning_mood"]].merge(
        prior, on=["date", "child"], how="inner")


plot_df = build_plot_df(df)
c1, c2 = st.columns(2)
if plot_df.empty:
    st.info("No plot data yet - need entries on consecutive days.")
else:
    plot_df["date"] = plot_df["date"].dt.strftime("%Y-%m-%d")
    fig_sleep = px.scatter(
        plot_df, x="prior_night_sleep_score", y="morning_mood", color="child",
        hover_data={"date": True},
        title="Morning Mood vs Prior Night Sleep Score",
        labels={"prior_night_sleep_score": "Prior Night Sleep (score)",
                "morning_mood": "Morning Mood (1-10)", "date": "Date"},
        range_y=[0, 11], range_x=[4, 11],
    )
    fig_eat = px.scatter(
        plot_df, x="prior_day_eating", y="morning_mood", color="child",
        hover_data={"date": True},
        title="Morning Mood vs Prior Day Eating",
        labels={"prior_day_eating": "Prior Day Eating (1-10)",
                "morning_mood": "Morning Mood (1-10)", "date": "Date"},
        range_y=[0, 11], range_x=[0, 11],
    )
    c1.plotly_chart(fig_sleep, use_container_width=True)
    c2.plotly_chart(fig_eat, use_container_width=True)

# ---- Download ----
buf = io.StringIO()
buf.write("# Entries\n")
df.to_csv(buf, index=False)
buf.write("\n# Bedtime to Sleep Score Mapping\n")
pd.DataFrame(BEDTIME_MAPPING).to_csv(buf, index=False)
# data-URI link instead of st.download_button, which 404s under stlite
b64 = base64.b64encode(buf.getvalue().encode()).decode()
st.markdown(
    f'<a download="sleep_food_data.csv" '
    f'href="data:text/csv;base64,{b64}">Download data (CSV)</a>',
    unsafe_allow_html=True,
)
