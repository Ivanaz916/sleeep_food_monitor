import calendar
import io
import os
from datetime import date, datetime, timedelta

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import ALL, Input, Output, State, ctx, dcc, html

DATA_FILE = os.path.join(os.path.dirname(__file__), "entries.csv")

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


def bedtime_to_score(bedtime_str):
    """bedtime_str is 'HH:MM' 24h. Earlier than 8:45 PM scores 10."""
    h, m = map(int, bedtime_str.split(":"))
    minutes = h * 60 + m
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
        df = pd.read_csv(DATA_FILE, dtype={"date": str, "bedtime": str})
        return df
    return pd.DataFrame(columns=COLUMNS)


def save_data(df):
    df.to_csv(DATA_FILE, index=False)


# Bootstrap is served locally from assets/bootstrap.min.css
app = dash.Dash(__name__)
app.title = "Sleep & Food Monitor"


def build_calendar(year, month, df):
    """Month grid of day buttons; days with entries are highlighted."""
    dates_with_entries = set(df["date"]) if not df.empty else set()
    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    header = dbc.Row(
        [dbc.Col(html.Strong(d), className="text-center") for d in
         ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]],
        className="mb-1",
    )
    rows = [header]
    for week in cal.monthdayscalendar(year, month):
        cols = []
        for day in week:
            if day == 0:
                cols.append(dbc.Col(html.Div(), className="p-1"))
            else:
                iso = f"{year:04d}-{month:02d}-{day:02d}"
                has_entry = iso in dates_with_entries
                cols.append(
                    dbc.Col(
                        dbc.Button(
                            str(day),
                            id={"type": "day-btn", "date": iso},
                            color="success" if has_entry else "light",
                            className="w-100",
                            size="sm",
                        ),
                        className="p-1",
                    )
                )
        rows.append(dbc.Row(cols))
    return html.Div(rows)


form_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle(id="modal-title")),
        dbc.ModalBody(
            [
                dbc.Label("Child"),
                dcc.Dropdown(
                    id="input-child",
                    options=[{"label": c, "value": c} for c in ["NR", "MR"]],
                    value="NR",
                    clearable=False,
                ),
                dbc.Label("Dinner completeness (1-10, 10 = highly complete)",
                          className="mt-3"),
                dcc.Slider(id="input-dinner", min=1, max=10, step=1, value=10,
                           marks={i: str(i) for i in range(1, 11)}),
                dbc.Label("Night wakings", className="mt-3"),
                dbc.Input(id="input-wakings", type="number", min=0, step=1,
                          value=0),
                dbc.Label("Bedtime", className="mt-3"),
                dbc.Input(id="input-bedtime", type="time", value="20:30"),
                dbc.Label("Following Morning mood (1-10, 10 = great mood)",
                          className="mt-3"),
                dcc.Slider(id="input-mood", min=1, max=10, step=1, value=10,
                           marks={i: str(i) for i in range(1, 11)}),
                html.Div(id="save-status", className="mt-2 text-success"),
            ]
        ),
        dbc.ModalFooter(
            [
                dbc.Button("Clear", id="btn-clear", color="warning",
                           className="me-auto"),
                dbc.Button("Cancel", id="btn-cancel", color="secondary"),
                dbc.Button("Save", id="btn-save", color="primary"),
            ]
        ),
    ],
    id="entry-modal",
    is_open=False,
)

today = date.today()

app.layout = dbc.Container(
    [
        dcc.Store(id="store-month", data={"year": today.year, "month": today.month}),
        dcc.Store(id="store-selected-date"),
        dcc.Store(id="store-data-version", data=0),
        html.H2("Sleep & Food Monitor", className="my-3"),
        dbc.Card(
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(dbc.Button("<", id="btn-prev-month",
                                               color="secondary", size="sm"),
                                    width="auto"),
                            dbc.Col(html.H5(id="month-label",
                                            className="text-center mb-0")),
                            dbc.Col(dbc.Button(">", id="btn-next-month",
                                               color="secondary", size="sm"),
                                    width="auto"),
                        ],
                        className="align-items-center mb-2",
                        justify="between",
                    ),
                    html.Div(id="calendar-grid"),
                    html.Small("Click a date to add or edit an entry. "
                               "Green = has entry.", className="text-muted"),
                ]
            ),
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(dcc.Graph(id="graph-mood-sleep"), md=6),
                dbc.Col(dcc.Graph(id="graph-mood-eating"), md=6),
            ]
        ),
        dbc.Button("Download data (CSV)", id="btn-download", color="info",
                   className="mb-4"),
        dcc.Download(id="download-csv"),
        form_modal,
    ],
    fluid=False,
)


@app.callback(
    Output("store-month", "data"),
    Input("btn-prev-month", "n_clicks"),
    Input("btn-next-month", "n_clicks"),
    State("store-month", "data"),
    prevent_initial_call=True,
)
def change_month(prev_clicks, next_clicks, month_data):
    y, m = month_data["year"], month_data["month"]
    if ctx.triggered_id == "btn-prev-month":
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    else:
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return {"year": y, "month": m}


@app.callback(
    Output("calendar-grid", "children"),
    Output("month-label", "children"),
    Input("store-month", "data"),
    Input("store-data-version", "data"),
)
def render_calendar(month_data, _version):
    y, m = month_data["year"], month_data["month"]
    df = load_data()
    label = f"{calendar.month_name[m]} {y}"
    return build_calendar(y, m, df), label


@app.callback(
    Output("entry-modal", "is_open"),
    Output("store-selected-date", "data"),
    Output("modal-title", "children"),
    Input({"type": "day-btn", "date": ALL}, "n_clicks"),
    Input("btn-cancel", "n_clicks"),
    Input("btn-save", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_modal(day_clicks, cancel, save):
    trig = ctx.triggered_id
    if trig in ("btn-cancel", "btn-save"):
        return False, dash.no_update, dash.no_update
    # Ignore the spurious trigger fired when buttons are first rendered
    if not any(c for c in day_clicks if c):
        return dash.no_update, dash.no_update, dash.no_update
    selected = trig["date"]
    return True, selected, f"Entry for {selected}"


@app.callback(
    Output("input-mood", "value"),
    Output("input-dinner", "value"),
    Output("input-wakings", "value"),
    Output("input-bedtime", "value"),
    Input("store-selected-date", "data"),
    Input("input-child", "value"),
    Input("btn-clear", "n_clicks"),
)
def prefill_form(selected_date, child, clear_clicks):
    defaults = (10, 10, 0, "20:30")
    if ctx.triggered_id == "btn-clear" or not selected_date:
        return defaults
    df = load_data()
    match = df[(df["date"] == selected_date) & (df["child"] == child)]
    if match.empty:
        return defaults
    row = match.iloc[0]
    return (int(row["morning_mood"]), int(row["dinner_completeness"]),
            int(row["night_wakings"]), row["bedtime"])


@app.callback(
    Output("store-data-version", "data"),
    Input("btn-save", "n_clicks"),
    Input("btn-clear", "n_clicks"),
    State("store-selected-date", "data"),
    State("input-child", "value"),
    State("input-mood", "value"),
    State("input-dinner", "value"),
    State("input-wakings", "value"),
    State("input-bedtime", "value"),
    State("store-data-version", "data"),
    prevent_initial_call=True,
)
def save_entry(save_clicks, clear_clicks, selected_date, child, mood, dinner,
               wakings, bedtime, version):
    if not selected_date:
        return dash.no_update
    df = load_data()
    # Remove existing row for this (date, child)
    df = df[~((df["date"] == selected_date) & (df["child"] == child))]
    if ctx.triggered_id == "btn-clear":
        save_data(df)
        return version + 1
    if not bedtime:
        return dash.no_update
    new_row = {
        "date": selected_date,
        "child": child,
        "morning_mood": mood,
        "dinner_completeness": dinner,
        "night_wakings": wakings or 0,
        "bedtime": bedtime,
        "sleep_score": bedtime_to_score(bedtime),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values(["date", "child"])
    save_data(df)
    return version + 1


def build_plot_df(df):
    """Join each day's mood with the prior day's dinner/sleep per child."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    prior = df[["date", "child", "dinner_completeness", "sleep_score"]].copy()
    prior["date"] = prior["date"] + timedelta(days=1)
    prior = prior.rename(columns={
        "dinner_completeness": "prior_day_eating",
        "sleep_score": "prior_night_sleep_score",
    })
    merged = df[["date", "child", "morning_mood"]].merge(
        prior, on=["date", "child"], how="inner")
    return merged


@app.callback(
    Output("graph-mood-sleep", "figure"),
    Output("graph-mood-eating", "figure"),
    Input("store-data-version", "data"),
)
def update_graphs(_version):
    df = build_plot_df(load_data())
    if df.empty:
        empty = px.scatter(title="No data yet - need entries on consecutive days")
        return empty, empty
    fig_sleep = px.scatter(
        df, x="prior_night_sleep_score", y="morning_mood", color="child",
        title="Morning Mood vs Prior Night Sleep Score",
        labels={"prior_night_sleep_score": "Prior Night Sleep (score)",
                "morning_mood": "Morning Mood (1-10)"},
        range_y=[0, 11], range_x=[4, 11],
    )
    fig_eat = px.scatter(
        df, x="prior_day_eating", y="morning_mood", color="child",
        title="Morning Mood vs Prior Day Eating",
        labels={"prior_day_eating": "Prior Day Eating (1-10)",
                "morning_mood": "Morning Mood (1-10)"},
        range_y=[0, 11], range_x=[0, 11],
    )
    return fig_sleep, fig_eat


@app.callback(
    Output("download-csv", "data"),
    Input("btn-download", "n_clicks"),
    prevent_initial_call=True,
)
def download_csv(n_clicks):
    df = load_data()
    mapping_df = pd.DataFrame(BEDTIME_MAPPING)
    buf = io.StringIO()
    buf.write("# Entries\n")
    df.to_csv(buf, index=False)
    buf.write("\n# Bedtime to Sleep Score Mapping\n")
    mapping_df.to_csv(buf, index=False)
    return dict(content=buf.getvalue(), filename="sleep_food_data.csv")


if __name__ == "__main__":
    app.run(debug=True)
