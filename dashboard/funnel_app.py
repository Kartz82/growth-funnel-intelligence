import plotly.io as pio
import os
import pandas as pd
import psycopg2
from psycopg2 import sql
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

DB_URI = "postgresql://postgres:postgres@localhost:5435/growth_funnel_db"

def get_conn():
    return psycopg2.connect(DB_URI)

def query(q):
    conn = get_conn()
    df = pd.read_sql(q, conn)
    conn.close()
    return df

# ── Data pulls ────────────────────────────────────────────────────────────────
def get_funnel():
    return query("SELECT * FROM v_growth_funnel_leakage ORDER BY total_sessions DESC")

def get_attribution():
    return query("SELECT * FROM v_marketing_channel_attribution ORDER BY last_touch_conversions DESC")

def get_cohorts():
    return query("SELECT * FROM v_behavioral_cohort_velocity ORDER BY engagement_tier, absolute_session_volume DESC")

def get_experiment():
    return pd.read_csv("data/models/experiment_results.csv")

def get_kpis():
    return query("""
        SELECT
            COUNT(DISTINCT session_id) AS total_sessions,
            COUNT(DISTINCT user_pseudo_id) AS unique_users,
            SUM(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) AS total_purchases,
            ROUND(
                100.0 * SUM(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(DISTINCT session_id), 0), 3
            ) AS macro_cvr_pct
        FROM raw_ga4_events
    """)

from PIL import Image
import io

def fig_to_img(fig, width=1400, height=600):
    """Convert plotly figure to PIL Image."""
    img_bytes = pio.to_image(fig, format="png", width=width, height=height, scale=2)
    return Image.open(io.BytesIO(img_bytes))

def stack_images(images, output_path):
    """Vertically stack PIL images and save."""
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)
    combined = Image.new("RGB", (max_width, total_height), color=(15, 17, 23))
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height
    combined.save(output_path)
    print(f"✅ Saved: {output_path}")

BACKGROUND = "#050A14"
PANEL = "#0B1220"
GRID = "rgba(148, 163, 184, 0.18)"
TEXT = "#E5E7EB"
MUTED = "#94A3B8"

TEAL = "#14B8A6"
GREEN = "#10B981"
ORANGE = "#F97316"
AMBER = "#F59E0B"
ROSE = "#FB7185"
RED = "#F43F5E"
GRAY = "#64748B"

def apply_portfolio_layout(fig, title, yaxis_title=None, xaxis_title=None, showlegend=False):
    fig.update_layout(
        title=dict(text=title, x=0.04, xanchor="left", font=dict(size=34, color=TEXT)),
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT, family="Arial, sans-serif", size=18),
        margin=dict(l=90, r=60, t=115, b=105),
        width=1600,
        height=900,
        showlegend=showlegend,
        bargap=0.55,
    )
    fig.update_xaxes(
        title=dict(text=xaxis_title, font=dict(color=MUTED, size=16)),
        tickfont=dict(color=TEXT, size=17),
        showgrid=False,
        zeroline=False,
        linecolor=GRID,
    )
    fig.update_yaxes(
        title=dict(text=yaxis_title, font=dict(color=MUTED, size=16)),
        tickfont=dict(color=TEXT, size=16),
        gridcolor=GRID,
        zeroline=False,
        linecolor=GRID,
    )
    return fig

def get_portfolio_funnel_data():
    try:
        return get_funnel()
    except psycopg2.OperationalError:
        events = pd.read_csv("data/transformed/flattened_events.csv")
        milestones = events.groupby(["session_id", "traffic_source_medium", "device_category"]).agg(
            stage_1_start=("event_name", lambda s: (s == "session_start").max()),
            stage_2_view=("event_name", lambda s: (s == "view_item").max()),
            stage_3_cart=("event_name", lambda s: (s == "add_to_cart").max()),
            stage_4_checkout=("event_name", lambda s: (s == "begin_checkout").max()),
            stage_5_purchase=("event_name", lambda s: (s == "purchase").max()),
        ).reset_index()
        df = milestones.groupby(["traffic_source_medium", "device_category"]).agg(
            total_sessions=("session_id", "nunique"),
            base_traffic=("stage_1_start", "sum"),
            product_views=("stage_2_view", "sum"),
            cart_additions=("stage_3_cart", "sum"),
            checkout_initiations=("stage_4_checkout", "sum"),
            realized_purchases=("stage_5_purchase", "sum"),
        ).reset_index()
        df = df.rename(columns={"traffic_source_medium": "acquisition_channel"})
        df["landing_to_view_drop_pct"] = (1 - df["product_views"] / df["base_traffic"].replace(0, pd.NA)) * 100
        df["product_to_cart_drop_pct"] = (1 - df["cart_additions"] / df["product_views"].replace(0, pd.NA)) * 100
        df["cart_to_checkout_drop_pct"] = (1 - df["checkout_initiations"] / df["cart_additions"].replace(0, pd.NA)) * 100
        df["checkout_to_purchase_drop_pct"] = (1 - df["realized_purchases"] / df["checkout_initiations"].replace(0, pd.NA)) * 100
        df["macro_conversion_rate_pct"] = df["realized_purchases"] / df["base_traffic"].replace(0, pd.NA) * 100
        return df.round({
            "landing_to_view_drop_pct": 2,
            "product_to_cart_drop_pct": 2,
            "cart_to_checkout_drop_pct": 2,
            "checkout_to_purchase_drop_pct": 2,
            "macro_conversion_rate_pct": 3,
        }).sort_values("total_sessions", ascending=False)

def get_portfolio_attribution_data():
    try:
        return get_attribution()
    except psycopg2.OperationalError:
        events = pd.read_csv("data/transformed/flattened_events.csv")
        events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])
        purchases = events[events["event_name"] == "purchase"][
            ["user_pseudo_id", "session_id", "event_timestamp"]
        ].rename(columns={"session_id": "purchase_session_id", "event_timestamp": "purchase_timestamp"})

        rows = []
        for purchase in purchases.itertuples(index=False):
            touchpoints = events[
                (events["user_pseudo_id"] == purchase.user_pseudo_id)
                & (events["event_timestamp"] <= purchase.purchase_timestamp)
            ].sort_values("event_timestamp")
            if touchpoints.empty:
                continue
            rows.append({
                "user_pseudo_id": purchase.user_pseudo_id,
                "first_touch_medium": touchpoints.iloc[0]["traffic_source_medium"],
                "last_touch_medium": touchpoints.iloc[-1]["traffic_source_medium"],
            })

        touches = pd.DataFrame(rows)
        first = touches.groupby("first_touch_medium")["user_pseudo_id"].nunique()
        last = touches.groupby("last_touch_medium")["user_pseudo_id"].nunique()
        df = pd.concat([first, last], axis=1).fillna(0).astype(int).reset_index()
        df.columns = ["marketing_channel", "first_touch_conversions", "last_touch_conversions"]
        df["attribution_delta"] = df["last_touch_conversions"] - df["first_touch_conversions"]
        return df.sort_values("last_touch_conversions", ascending=False)

def save_portfolio_charts():
    os.makedirs("reports", exist_ok=True)

    df = get_portfolio_funnel_data()
    drop_cols = ["landing_to_view_drop_pct","product_to_cart_drop_pct",
                 "cart_to_checkout_drop_pct","checkout_to_purchase_drop_pct"]
    drop_labels = ["Landing to View","View to Cart","Cart to Checkout","Checkout to Purchase"]
    avg_drops = df[drop_cols].mean()
    largest_drop = avg_drops.max()
    drop_colors = [RED if v == largest_drop else AMBER for v in avg_drops.values]

    fig_drop = go.Figure(go.Bar(
        x=drop_labels,
        y=avg_drops.values,
        marker=dict(color=drop_colors, line=dict(color="rgba(255,255,255,0.10)", width=1)),
        text=[f"{v:.1f}%" for v in avg_drops.values],
        textposition="outside",
        width=0.42,
        cliponaxis=False,
    ))
    apply_portfolio_layout(fig_drop, "Funnel Drop-off by Stage", yaxis_title="Drop-off %")
    fig_drop.update_yaxes(range=[0, max(110, largest_drop + 12)])
    pio.write_image(fig_drop, "reports/funnel_dropoff.png", width=1600, height=900, scale=2)
    print("✅ Saved: reports/funnel_dropoff.png")

    df3 = get_portfolio_attribution_data()
    channel_labels = df3["marketing_channel"].astype(str).str.replace("_", " ", regex=False).str.title()
    delta_colors = [TEAL if v >= 0 else ORANGE for v in df3["attribution_delta"]]

    fig_delta = go.Figure(go.Bar(
        x=channel_labels,
        y=df3["attribution_delta"],
        marker=dict(color=delta_colors, line=dict(color="rgba(255,255,255,0.10)", width=1)),
        text=[f"{int(v):+d}" for v in df3["attribution_delta"]],
        textposition="outside",
        width=0.42,
        cliponaxis=False,
    ))
    fig_delta.add_hline(y=0, line_color=GRAY, line_width=2)
    apply_portfolio_layout(fig_delta, "Channel Attribution Shift", yaxis_title="Last-touch minus first-touch conversions")
    fig_delta.update_xaxes(tickangle=-20)
    pio.write_image(fig_delta, "reports/channel_attribution.png", width=1600, height=900, scale=2)
    print("✅ Saved: reports/channel_attribution.png")

    df5 = get_experiment()
    lift_colors = [GREEN if v >= 0 else ROSE for v in df5["Relative_Lift_Pct"]]

    fig_lift = go.Figure(go.Bar(
        x=df5["Funnel_Conversion_Step"],
        y=df5["Relative_Lift_Pct"],
        marker=dict(color=lift_colors, line=dict(color="rgba(255,255,255,0.10)", width=1)),
        text=[f"{v:+.2f}%" for v in df5["Relative_Lift_Pct"]],
        textposition="outside",
        width=0.42,
        cliponaxis=False,
    ))
    fig_lift.add_hline(y=0, line_color=GRAY, line_width=2)
    apply_portfolio_layout(fig_lift, "Experiment Lift by Funnel Stage", yaxis_title="Relative lift %")
    fig_lift.update_layout(
        annotations=[
            dict(
                text="No statistically significant uplift detected",
                x=0.04,
                y=1.055,
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="left",
                font=dict(color=MUTED, size=18),
            )
        ]
    )
    fig_lift.update_xaxes(tickangle=-12)
    pio.write_image(fig_lift, "reports/experiment_results.png", width=1600, height=900, scale=2)
    print("✅ Saved: reports/experiment_results.png")

def save_all_reports():
    os.makedirs("reports", exist_ok=True)

    # ── Page 1: Executive KPIs ─────────────────────────────────────────────
    kpi = get_kpis().iloc[0]
    monthly = query("""
        SELECT DATE_TRUNC('week', event_timestamp) AS week,
               COUNT(DISTINCT session_id) AS sessions,
               SUM(CASE WHEN event_name='purchase' THEN 1 ELSE 0 END) AS purchases
        FROM raw_ga4_events GROUP BY 1 ORDER BY 1
    """)
    top_countries = query("""
        SELECT geo_country, COUNT(DISTINCT session_id) AS sessions
        FROM raw_ga4_events
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """)

    # KPI scorecard as a table figure
    fig_kpi = go.Figure(data=[go.Table(
        header=dict(
            values=["Total Sessions", "Unique Users", "Total Purchases", "Macro CVR %"],
            fill_color="#1a1d27", font=dict(color="#00d4ff", size=14), height=40
        ),
        cells=dict(
            values=[
                [f"{int(kpi['total_sessions']):,}"],
                [f"{int(kpi['unique_users']):,}"],
                [f"{int(kpi['total_purchases']):,}"],
                [f"{kpi['macro_cvr_pct']}%"]
            ],
            fill_color="#0f1117", font=dict(color="white", size=16), height=50
        )
    )])
    fig_kpi.update_layout(title="Executive KPI Summary",
                          paper_bgcolor="#0f1117", margin=dict(t=40, b=10))

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=monthly["week"], y=monthly["sessions"],
                                  name="Sessions", line=dict(color="#00d4ff", width=2)))
    fig_line.add_trace(go.Scatter(x=monthly["week"], y=monthly["purchases"],
                                  name="Purchases", line=dict(color="#ff6b6b", width=2),
                                  yaxis="y2"))
    fig_line.update_layout(
        title="Weekly Sessions vs Purchases",
        paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27", font_color="#ccc",
        yaxis=dict(title="Sessions", color="#00d4ff"),
        yaxis2=dict(title="Purchases", overlaying="y", side="right", color="#ff6b6b"),
        margin=dict(t=40, b=20)
    )

    fig_bar = px.bar(top_countries, x="sessions", y="geo_country", orientation="h",
                     color="sessions", color_continuous_scale="Blues",
                     title="Top 10 Countries by Sessions")
    fig_bar.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                          font_color="#ccc", yaxis=dict(autorange="reversed"),
                          margin=dict(t=40, b=20))

    stack_images(
        [fig_to_img(fig_kpi, height=200), fig_to_img(fig_line), fig_to_img(fig_bar)],
        "reports/01_executive_kpi.png"
    )

    # ── Page 2: Funnel Leakage ─────────────────────────────────────────────
    df = get_funnel()

    device_filter = df.groupby("device_category").agg(
        base_traffic=("base_traffic","sum"),
        product_views=("product_views","sum"),
        cart_additions=("cart_additions","sum"),
        checkout_initiations=("checkout_initiations","sum"),
        realized_purchases=("realized_purchases","sum")
    ).reset_index()
    stages = ["base_traffic","product_views","cart_additions",
              "checkout_initiations","realized_purchases"]
    labels = ["Sessions","Views","Add to Cart","Checkout","Purchase"]

    fig_funnel = go.Figure()
    for device in device_filter["device_category"].unique():
        row = device_filter[device_filter["device_category"] == device].iloc[0]
        fig_funnel.add_trace(go.Bar(name=device, x=labels,
                                    y=[row[s] for s in stages]))
    fig_funnel.update_layout(barmode="group", paper_bgcolor="#0f1117",
                              plot_bgcolor="#1a1d27", font_color="#ccc",
                              title="Funnel Volume by Device", margin=dict(t=40, b=20))

    drop_cols = ["landing_to_view_drop_pct","product_to_cart_drop_pct",
                 "cart_to_checkout_drop_pct","checkout_to_purchase_drop_pct"]
    drop_labels = ["Landing→View","View→Cart","Cart→Checkout","Checkout→Purchase"]
    avg_drops = df[drop_cols].mean()
    fig_drop = go.Figure(go.Bar(
        x=drop_labels, y=avg_drops.values,
        marker_color=["#ff6b6b" if v > 70 else "#ffd700" if v > 40 else "#a8ff78"
                      for v in avg_drops.values],
        text=[f"{v:.1f}%" for v in avg_drops.values], textposition="outside"
    ))
    fig_drop.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", title="Average Drop-off % Per Funnel Stage",
                           yaxis=dict(range=[0, 110]), margin=dict(t=40, b=20))

    tbl = df[["acquisition_channel","device_category","total_sessions",
              "realized_purchases","macro_conversion_rate_pct"]].copy()
    tbl.columns = ["Channel","Device","Sessions","Purchases","CVR %"]
    fig_tbl = go.Figure(data=[go.Table(
        header=dict(values=list(tbl.columns),
                    fill_color="#1a1d27", font=dict(color="#00d4ff", size=12), height=35),
        cells=dict(values=[tbl[c] for c in tbl.columns],
                   fill_color="#0f1117", font=dict(color="white", size=11), height=28)
    )])
    fig_tbl.update_layout(title="Funnel Breakdown by Channel & Device",
                          paper_bgcolor="#0f1117", margin=dict(t=40, b=10))

    stack_images(
        [fig_to_img(fig_funnel), fig_to_img(fig_drop), fig_to_img(fig_tbl, height=500)],
        "reports/02_funnel_leakage.png"
    )

    # ── Page 3: Channel Attribution ────────────────────────────────────────
    df3 = get_attribution()

    fig_attr = go.Figure()
    fig_attr.add_trace(go.Bar(name="First Touch", x=df3["marketing_channel"],
                              y=df3["first_touch_conversions"], marker_color="#00d4ff"))
    fig_attr.add_trace(go.Bar(name="Last Touch",  x=df3["marketing_channel"],
                              y=df3["last_touch_conversions"], marker_color="#ff6b6b"))
    fig_attr.update_layout(barmode="group", paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", title="First-Touch vs Last-Touch Conversions",
                           margin=dict(t=40, b=20))

    fig_delta = px.bar(df3, x="marketing_channel", y="attribution_delta",
                       color="attribution_delta", color_continuous_scale="RdYlGn",
                       title="Attribution Delta (Last - First Touch)")
    fig_delta.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                            font_color="#ccc", margin=dict(t=40, b=20))

    stack_images(
        [fig_to_img(fig_attr), fig_to_img(fig_delta)],
        "reports/03_channel_attribution.png"
    )

    # ── Page 4: Behavioral Cohorts ─────────────────────────────────────────
    df4 = get_cohorts()

    fig_cvr = px.bar(df4, x="engagement_tier", y="absolute_conversion_rate_pct",
                     color="device_category", barmode="group",
                     title="Conversion Rate % by Engagement Tier & Device",
                     color_discrete_sequence=["#00d4ff", "#ff6b6b", "#ffd700"])
    fig_cvr.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                          font_color="#ccc", margin=dict(t=40, b=20))

    fig_cart = px.bar(df4, x="engagement_tier", y="cart_add_rate_pct",
                      color="device_category", barmode="group",
                      title="Cart Add Rate % by Engagement Tier & Device",
                      color_discrete_sequence=["#00d4ff", "#ff6b6b", "#ffd700"])
    fig_cart.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", margin=dict(t=40, b=20))

    heat_data = df4.pivot_table(index="engagement_tier", columns="device_category",
                                values="absolute_conversion_rate_pct", aggfunc="mean")
    fig_heat = px.imshow(heat_data, color_continuous_scale="Blues",
                         title="Conversion Rate Heatmap: Tier × Device")
    fig_heat.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", margin=dict(t=40, b=20))

    stack_images(
        [fig_to_img(fig_cvr), fig_to_img(fig_cart), fig_to_img(fig_heat)],
        "reports/04_behavioral_cohorts.png"
    )

    # ── Page 5: A/B Experiment ─────────────────────────────────────────────
    df5 = get_experiment()
    colors = ["#a8ff78" if s == "SIGNIFICANT" else "#ff6b6b"
              for s in df5["Statistical_Significance"]]

    fig_lift = go.Figure(go.Bar(
        x=df5["Funnel_Conversion_Step"], y=df5["Relative_Lift_Pct"],
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in df5["Relative_Lift_Pct"]],
        textposition="outside"
    ))
    fig_lift.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", title="Relative Lift % by Funnel Stage",
                           yaxis=dict(title="Lift %"), margin=dict(t=40, b=60))

    fig_pval = go.Figure(go.Bar(
        x=df5["Funnel_Conversion_Step"], y=df5["P_Value"],
        marker_color=["#00d4ff" if p < 0.05 else "#555" for p in df5["P_Value"]],
        text=[f"{p:.4f}" for p in df5["P_Value"]], textposition="outside"
    ))
    fig_pval.add_hline(y=0.05, line_dash="dash", line_color="#ffd700",
                       annotation_text="α = 0.05")
    fig_pval.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
                           font_color="#ccc", title="P-Values by Funnel Stage",
                           yaxis=dict(range=[0, 1.1]), margin=dict(t=40, b=60))

    tbl5 = df5[["Funnel_Conversion_Step","Control_CR_Pct","Variant_CR_Pct",
                "Relative_Lift_Pct","Z_Score","P_Value","Statistical_Significance"]]
    tbl5.columns = ["Step","Control CR%","Variant CR%","Lift%","Z-Score","P-Value","Result"]
    fig_tbl5 = go.Figure(data=[go.Table(
        header=dict(values=list(tbl5.columns),
                    fill_color="#1a1d27", font=dict(color="#00d4ff", size=12), height=35),
        cells=dict(values=[tbl5[c] for c in tbl5.columns],
                   fill_color="#0f1117", font=dict(color="white", size=11), height=28)
    )])
    fig_tbl5.update_layout(title="Full Experiment Results Matrix",
                           paper_bgcolor="#0f1117", margin=dict(t=40, b=10))

    stack_images(
        [fig_to_img(fig_lift), fig_to_img(fig_pval), fig_to_img(fig_tbl5, height=400)],
        "reports/05_ab_experiment.png"
    )

    print("\n🎉 All 5 full-page reports exported to reports/")

# ── App init ──────────────────────────────────────────────────────────────────
app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG],
           suppress_callback_exceptions=True)
app.title = "Growth Funnel Intelligence Engine"

ACCENT = "#00d4ff"
BG = "#0f1117"
CARD = "#1a1d27"

def kpi_card(title, value, color=ACCENT):
    return dbc.Card([
        dbc.CardBody([
            html.P(title, style={"color": "#aaa", "fontSize": "13px", "marginBottom": "4px"}),
            html.H3(value, style={"color": color, "fontWeight": "700", "margin": 0})
        ])
    ], style={"background": CARD, "border": f"1px solid {color}33", "borderRadius": "12px"})

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H2("⚡ Growth Funnel Intelligence Engine",
                        style={"color": ACCENT, "fontWeight": "700", "padding": "24px 0 8px"}))
    ]),

    dbc.Row([
        dbc.Col(dbc.Tabs(id="tabs", active_tab="tab-exec", children=[
            dbc.Tab(label="Executive KPIs",       tab_id="tab-exec"),
            dbc.Tab(label="Funnel Leakage",       tab_id="tab-funnel"),
            dbc.Tab(label="Channel Attribution",  tab_id="tab-channel"),
            dbc.Tab(label="Behavioral Cohorts",   tab_id="tab-cohort"),
            dbc.Tab(label="A/B Experiment",       tab_id="tab-ab"),
        ]))
    ], className="mb-3"),

    html.Div(id="tab-content")

], fluid=True, style={"background": BG, "minHeight": "100vh", "padding": "0 24px"})

# ── Tab router ────────────────────────────────────────────────────────────────
@app.callback(Output("tab-content", "children"), Input("tabs", "active_tab"))
def render(tab):
    if tab == "tab-exec":   return exec_page()
    if tab == "tab-funnel": return funnel_page()
    if tab == "tab-channel":return channel_page()
    if tab == "tab-cohort": return cohort_page()
    if tab == "tab-ab":     return ab_page()

# ── Page 1 — Executive KPIs ───────────────────────────────────────────────────
def exec_page():
    kpi = get_kpis().iloc[0]
    funnel = get_funnel()

    monthly = query("""
        SELECT
            DATE_TRUNC('week', event_timestamp) AS week,
            COUNT(DISTINCT session_id) AS sessions,
            SUM(CASE WHEN event_name='purchase' THEN 1 ELSE 0 END) AS purchases
        FROM raw_ga4_events
        GROUP BY 1 ORDER BY 1
    """)

    line = go.Figure()
    line.add_trace(go.Scatter(x=monthly["week"], y=monthly["sessions"],
                              name="Sessions", line=dict(color=ACCENT, width=2)))
    line.add_trace(go.Scatter(x=monthly["week"], y=monthly["purchases"],
                              name="Purchases", line=dict(color="#ff6b6b", width=2),
                              yaxis="y2"))
    line.update_layout(
        paper_bgcolor=CARD, plot_bgcolor=CARD, font_color="#ccc",
        title="Weekly Sessions vs Purchases",
        yaxis=dict(title="Sessions", color=ACCENT),
        yaxis2=dict(title="Purchases", overlaying="y", side="right", color="#ff6b6b"),
        legend=dict(bgcolor=CARD),
        margin=dict(t=40, b=20)
    )

    top_countries = query("""
        SELECT geo_country, COUNT(DISTINCT session_id) AS sessions
        FROM raw_ga4_events
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """)
    bar = px.bar(top_countries, x="sessions", y="geo_country", orientation="h",
                 color="sessions", color_continuous_scale="Blues",
                 title="Top 10 Countries by Sessions")
    bar.update_layout(paper_bgcolor=CARD, plot_bgcolor=CARD,
                      font_color="#ccc", margin=dict(t=40, b=20),
                      yaxis=dict(autorange="reversed"))

    return html.Div([
        dbc.Row([
            dbc.Col(kpi_card("Total Sessions",  f"{int(kpi['total_sessions']):,}"), md=3),
            dbc.Col(kpi_card("Unique Users",    f"{int(kpi['unique_users']):,}"),   md=3),
            dbc.Col(kpi_card("Total Purchases", f"{int(kpi['total_purchases']):,}", "#a8ff78"), md=3),
            dbc.Col(kpi_card("Macro CVR",       f"{kpi['macro_cvr_pct']}%",        "#ffd700"), md=3),
        ], className="mb-4 g-3"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=line), md=8),
            dbc.Col(dcc.Graph(figure=bar),  md=4),
        ])
    ])

# ── Page 2 — Funnel Leakage ───────────────────────────────────────────────────
def funnel_page():
    df = get_funnel()

    device_filter = df.groupby("device_category").agg(
        base_traffic=("base_traffic","sum"),
        product_views=("product_views","sum"),
        cart_additions=("cart_additions","sum"),
        checkout_initiations=("checkout_initiations","sum"),
        realized_purchases=("realized_purchases","sum")
    ).reset_index()

    stages = ["base_traffic","product_views","cart_additions",
              "checkout_initiations","realized_purchases"]
    labels = ["Sessions","Views","Add to Cart","Checkout","Purchase"]

    fig_funnel = go.Figure()
    colors = [ACCENT, "#a8ff78", "#ffd700", "#ff9f43", "#ff6b6b"]
    for device in device_filter["device_category"].unique():
        row = device_filter[device_filter["device_category"] == device].iloc[0]
        fig_funnel.add_trace(go.Bar(
            name=device,
            x=labels,
            y=[row[s] for s in stages],
        ))
    fig_funnel.update_layout(
        barmode="group", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font_color="#ccc", title="Funnel Volume by Device",
        margin=dict(t=40, b=20)
    )

    drop_cols = ["landing_to_view_drop_pct","product_to_cart_drop_pct",
                 "cart_to_checkout_drop_pct","checkout_to_purchase_drop_pct"]
    drop_labels = ["Landing→View","View→Cart","Cart→Checkout","Checkout→Purchase"]

    avg_drops = df[drop_cols].mean()
    fig_drop = go.Figure(go.Bar(
        x=drop_labels, y=avg_drops.values,
        marker_color=["#ff6b6b" if v > 70 else "#ffd700" if v > 40 else "#a8ff78"
                      for v in avg_drops.values],
        text=[f"{v:.1f}%" for v in avg_drops.values],
        textposition="outside"
    ))
    fig_drop.update_layout(
        paper_bgcolor=CARD, plot_bgcolor=CARD, font_color="#ccc",
        title="Average Drop-off % Per Funnel Stage",
        yaxis=dict(title="Drop-off %", range=[0, 110]),
        margin=dict(t=40, b=20)
    )

    tbl = df[["acquisition_channel","device_category","total_sessions",
              "realized_purchases","macro_conversion_rate_pct"]].copy()
    tbl.columns = ["Channel","Device","Sessions","Purchases","CVR %"]

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_funnel), md=7),
            dbc.Col(dcc.Graph(figure=fig_drop),   md=5),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(html.Div([
                html.H5("Funnel Breakdown by Channel & Device",
                        style={"color": ACCENT, "marginBottom": "12px"}),
                dbc.Table.from_dataframe(tbl.head(20), striped=True, bordered=False,
                                         hover=True, size="sm")
            ]))
        ])
    ])

# ── Page 3 — Channel Attribution ─────────────────────────────────────────────
def channel_page():
    df = get_attribution()

    fig = go.Figure()
    fig.add_trace(go.Bar(name="First Touch", x=df["marketing_channel"],
                         y=df["first_touch_conversions"], marker_color=ACCENT))
    fig.add_trace(go.Bar(name="Last Touch",  x=df["marketing_channel"],
                         y=df["last_touch_conversions"], marker_color="#ff6b6b"))
    fig.update_layout(
        barmode="group", paper_bgcolor=CARD, plot_bgcolor=CARD,
        font_color="#ccc", title="First-Touch vs Last-Touch Conversions by Channel",
        margin=dict(t=40, b=20)
    )

    fig_delta = px.bar(df, x="marketing_channel", y="attribution_delta",
                       color="attribution_delta",
                       color_continuous_scale="RdYlGn",
                       title="Attribution Delta (Last - First Touch)")
    fig_delta.update_layout(paper_bgcolor=CARD, plot_bgcolor=CARD,
                             font_color="#ccc", margin=dict(t=40, b=20))

    return html.Div([
        dbc.Row([dbc.Col(dcc.Graph(figure=fig))],    className="mb-4"),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig_delta))])
    ])

# ── Page 4 — Behavioral Cohorts ───────────────────────────────────────────────
def cohort_page():
    df = get_cohorts()

    fig = px.bar(df, x="engagement_tier", y="absolute_conversion_rate_pct",
                 color="device_category", barmode="group",
                 title="Conversion Rate % by Engagement Tier & Device",
                 color_discrete_sequence=[ACCENT, "#ff6b6b", "#ffd700"])
    fig.update_layout(paper_bgcolor=CARD, plot_bgcolor=CARD,
                      font_color="#ccc", margin=dict(t=40, b=20))

    fig2 = px.bar(df, x="engagement_tier", y="cart_add_rate_pct",
                  color="device_category", barmode="group",
                  title="Cart Add Rate % by Engagement Tier & Device",
                  color_discrete_sequence=[ACCENT, "#ff6b6b", "#ffd700"])
    fig2.update_layout(paper_bgcolor=CARD, plot_bgcolor=CARD,
                       font_color="#ccc", margin=dict(t=40, b=20))

    heat_data = df.pivot_table(
        index="engagement_tier", columns="device_category",
        values="absolute_conversion_rate_pct", aggfunc="mean"
    )
    fig3 = px.imshow(heat_data, color_continuous_scale="Blues",
                     title="Conversion Rate Heatmap: Tier × Device")
    fig3.update_layout(paper_bgcolor=CARD, plot_bgcolor=CARD,
                       font_color="#ccc", margin=dict(t=40, b=20))

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig),  md=6),
            dbc.Col(dcc.Graph(figure=fig2), md=6),
        ], className="mb-4"),
        dbc.Row([dbc.Col(dcc.Graph(figure=fig3))])
    ])

# ── Page 5 — A/B Experiment ───────────────────────────────────────────────────
def ab_page():
    df = get_experiment()

    colors = ["#a8ff78" if s == "SIGNIFICANT" else "#ff6b6b"
              for s in df["Statistical_Significance"]]

    fig_lift = go.Figure(go.Bar(
        x=df["Funnel_Conversion_Step"],
        y=df["Relative_Lift_Pct"],
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in df["Relative_Lift_Pct"]],
        textposition="outside"
    ))
    fig_lift.update_layout(
        paper_bgcolor=CARD, plot_bgcolor=CARD, font_color="#ccc",
        title="Relative Lift % by Funnel Stage (Control vs Variant)",
        yaxis=dict(title="Lift %"),
        margin=dict(t=40, b=60)
    )

    fig_pval = go.Figure(go.Bar(
        x=df["Funnel_Conversion_Step"],
        y=df["P_Value"],
        marker_color=[ACCENT if p < 0.05 else "#555" for p in df["P_Value"]],
        text=[f"{p:.4f}" for p in df["P_Value"]],
        textposition="outside"
    ))
    fig_pval.add_hline(y=0.05, line_dash="dash", line_color="#ffd700",
                       annotation_text="α = 0.05 significance threshold")
    fig_pval.update_layout(
        paper_bgcolor=CARD, plot_bgcolor=CARD, font_color="#ccc",
        title="P-Values by Funnel Stage",
        yaxis=dict(title="P-Value", range=[0, 1.1]),
        margin=dict(t=40, b=60)
    )

    tbl = df[["Funnel_Conversion_Step","Control_CR_Pct","Variant_CR_Pct",
              "Relative_Lift_Pct","Z_Score","P_Value","Statistical_Significance"]]
    tbl.columns = ["Step","Control CR%","Variant CR%","Lift%","Z-Score","P-Value","Result"]

    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_lift),  md=6),
            dbc.Col(dcc.Graph(figure=fig_pval),  md=6),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col([
                html.H5("Full Experiment Results Matrix",
                        style={"color": ACCENT, "marginBottom": "12px"}),
                dbc.Table.from_dataframe(tbl, striped=True, bordered=False,
                                         hover=True, size="sm")
            ])
        ])
    ])
@app.server.route("/export")
def export_reports():
    save_all_reports()
    return "✅ Reports exported to reports/ folder"

if __name__ == "__main__":
    app.run(debug=True, port=8051)
