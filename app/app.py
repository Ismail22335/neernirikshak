"""
Tidewatch - waterborne outbreak early-warning dashboard
Two-stage pipeline from mini_project.ipynb:
  1) water sample (TDS min/max, turbidity)  -> potability model -> Potable_Predicted
  2) symptoms (0-3) + Potable_Predicted     -> outbreak model   -> outbreak probability
Run:  streamlit run app.py
"""
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")
HERE = Path(__file__).parent

st.set_page_config(page_title="Tidewatch", page_icon="💧", layout="wide")

# ----------------------------------------------------------------------------
# Palette: chart-room paper, deep ink, kelp (safe), coral (risk), brass (watch)
# ----------------------------------------------------------------------------
INK, PAPER, FOAM = "#0E2F44", "#EEF4F1", "#FFFFFF"
KELP, CORAL, BRASS = "#2E8B6A", "#E2553A", "#C79A1E"

SYMPTOMS = {
    "Nausea": "🤢",
    "Fever": "🌡️",
    "Dehydration": "🏜️",
    "Abdominal_Cramps": "🌀",
    "Diarrhoea": "🚽",
}
SEVERITY = ["None", "Mild", "Moderate", "Severe"]

PRESETS = {
    "Clear spring": dict(cmin=30, cmax=100, turb=8, sym=[0, 0, 0, 0, 0]),
    "Village pond, monsoon": dict(cmin=90, cmax=420, turb=62, sym=[1, 1, 1, 2, 2]),
    "Industrial runoff": dict(cmin=400, cmax=2400, turb=35, sym=[2, 1, 2, 2, 3]),
    "Clear water, sick clinic": dict(cmin=30, cmax=100, turb=8, sym=[2, 2, 3, 3, 3]),
}

# ----------------------------------------------------------------------------
# Styling
# ----------------------------------------------------------------------------
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Figtree:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp {{ font-family:'Figtree',sans-serif; color:{INK}; }}
.stApp {{ background:{PAPER}; }}
header[data-testid="stHeader"] {{ background:transparent; }}
h1,h2,h3,h4 {{ font-family:'Bricolage Grotesque',sans-serif !important; color:{INK}; letter-spacing:-0.02em; }}
.block-container {{ padding-top:1.4rem; max-width:1250px; }}

.hero {{ position:relative; overflow:hidden; border-radius:22px; padding:34px 38px; margin-bottom:18px;
  background:{INK}; color:#EAF6F2; }}
.hero svg.contours {{ position:absolute; inset:0; width:100%; height:100%; opacity:.22; }}
.hero h1 {{ color:#fff !important; font-size:3rem; margin:0; font-weight:800; }}
.hero p {{ margin:.5rem 0 0; max-width:640px; font-size:1.05rem; color:#BFD9D3; }}

.card {{ background:{FOAM}; border-radius:18px; padding:20px 22px; border:1px solid #D5E3DE; }}
.stage {{ display:flex; align-items:center; gap:14px; }}
.stage .num {{ width:34px; height:34px; border-radius:50%; background:{INK}; color:#fff;
  display:grid; place-items:center; font-family:'Bricolage Grotesque'; font-weight:700; flex:none; }}
.stage h4 {{ margin:0; font-size:1.15rem; }}
.stage small {{ color:#58727F; }}
.pipe {{ border-left:3px dashed #9DBBB3; margin:6px 0 6px 16px; padding:2px 0 2px 24px; color:#58727F; font-size:.9rem; }}

.verdict {{ border-radius:18px; padding:20px 24px; color:#fff; }}
.verdict h2 {{ color:#fff !important; margin:0 0 4px; font-size:1.7rem; }}
.verdict p {{ margin:0; opacity:.95; }}
.chip {{ display:inline-block; padding:3px 12px; border-radius:99px; font-weight:600; font-size:.85rem; }}

div[data-testid="stMetric"] {{ background:{FOAM}; border:1px solid #D5E3DE; border-radius:14px; padding:12px 16px; }}
.stTabs [data-baseweb="tab-list"] {{ gap:6px; }}
.stTabs [data-baseweb="tab"] {{ background:transparent; border-radius:10px; padding:8px 16px; font-weight:600; }}
.stTabs [aria-selected="true"] {{ background:{INK}; color:#fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}
.stButton>button {{ border-radius:12px; border:1px solid {INK}; font-weight:600; }}
@keyframes drift {{ from {{ transform:translateX(0); }} to {{ transform:translateX(-120px); }} }}
.wave {{ animation:drift 6s linear infinite; }}
@media (prefers-reduced-motion: reduce) {{ .wave {{ animation:none; }} }}
</style>
""",
    unsafe_allow_html=True,
)

CONTOURS = "".join(
    f'<ellipse cx="{760 + i*6}" cy="{150 - i*3}" rx="{60 + i*38}" ry="{30 + i*17}" fill="none" '
    f'stroke="#7FD1C0" stroke-width="1.2" transform="rotate({-12 + i*2} 760 150)"/>'
    for i in range(14)
)
st.markdown(
    f"""
<div class="hero">
  <svg class="contours" viewBox="0 0 1000 300" preserveAspectRatio="xMidYMid slice">{CONTOURS}</svg>
  <h1>Tidewatch</h1>
  <p>Test a water sample, add what people are reporting, and see how likely a waterborne outbreak is.
  Two models run in sequence: first is the water safe to drink, then do the symptoms point to an outbreak.</p>
</div>
""",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Models / data
# ----------------------------------------------------------------------------
def find(name: str) -> Path | None:
    for base in (HERE / "models", HERE):
        hits = sorted(base.glob(f"*{name}*"))
        if hits:
            return hits[0]
    return None


@st.cache_resource(show_spinner="Loading models...")
def load_models():
    pm, om = find("water_potability_model.pkl"), find("outbreak_prediction_model.pkl")
    if not pm or not om:
        return None, None
    return joblib.load(pm), joblib.load(om)


@st.cache_data
def load_data():
    out = {}
    for key, pat in [("water", "water_potability_dataset.csv"), ("sym", "outbreak_symptoms_dataset.csv")]:
        for base in (HERE / "data", HERE):
            hits = sorted(base.glob(f"*{pat}"))
            if hits:
                out[key] = pd.read_csv(hits[0])
                break
    return out


potability_model, outbreak_model = load_models()
if potability_model is None:
    st.error(
        "Model files not found. Put `water_potability_model.pkl` and `outbreak_prediction_model.pkl` "
        "in a `models/` folder next to `app.py`."
    )
    st.stop()
DATA = load_data()


# ----------------------------------------------------------------------------
# Pipeline helpers (mirrors the notebook: TDS = 0.64 x conductivity, log1p scale)
# ----------------------------------------------------------------------------
def water_frame(cmin, cmax, turb) -> pd.DataFrame:
    cmin, cmax, turb = (np.atleast_1d(np.asarray(v, dtype=float)) for v in (cmin, cmax, turb))
    return pd.DataFrame(
        {
            "TDS_estimated": np.log1p(cmax * 0.64),
            "TDS_estimated_min": np.log1p(cmin * 0.64),
            "Turbidity_synthetic": turb,
        }
    )


def run_pipeline(cmin, cmax, turb, symptoms):
    """symptoms: list of 5 ints (or 5 arrays) in SYMPTOMS order."""
    wf = water_frame(cmin, cmax, turb)
    p_potable = potability_model.predict_proba(wf)[:, 1]
    potable = potability_model.predict(wf)
    n = len(wf)
    sx = pd.DataFrame({k: np.broadcast_to(np.asarray(v), (n,)) for k, v in zip(SYMPTOMS, symptoms)})
    sx["Potable_Predicted"] = potable
    p_out = outbreak_model.predict_proba(sx[list(outbreak_model.feature_names_in_)])[:, 1]
    return p_potable, potable, p_out


def tone(p_out):
    if p_out < 0.30:
        return "Low risk", KELP, "No sign of an outbreak from this sample and these symptoms."
    if p_out < 0.60:
        return "Keep watching", BRASS, "Mixed signals. Re-test the water and check on the people reporting symptoms."
    return "Outbreak likely", CORAL, "Water and symptoms both point the same way. Treat as a possible outbreak and alert local health staff."


# ----------------------------------------------------------------------------
# The glass: cloudiness = turbidity, specks = dissolved solids
# ----------------------------------------------------------------------------
def glass_svg(turb, cmax, p_potable):
    cloud = min(turb / 80, 1)
    r = int(150 + (150 - 150) * cloud)  # aqua -> murky olive-brown
    col_clear, col_murky = (127, 209, 235), (150, 118, 70)
    mix = tuple(int(a + (b - a) * cloud) for a, b in zip(col_clear, col_murky))
    water = f"rgb{mix}"
    n_specks = int(np.clip(np.log1p(cmax) / np.log1p(4000) * 46, 3, 46))
    rng = np.random.default_rng(7)
    specks = "".join(
        f'<circle cx="{rng.uniform(78, 162):.0f}" cy="{rng.uniform(110, 245):.0f}" r="{rng.uniform(1, 2.6):.1f}" '
        f'fill="#3b2a14" opacity="{rng.uniform(.25, .6):.2f}"/>'
        for _ in range(n_specks)
    )
    badge = KELP if p_potable >= 0.5 else CORAL
    label = "Drinkable" if p_potable >= 0.5 else "Not drinkable"
    return f"""
<div class="card" style="text-align:center;padding:14px 10px 6px;">
<svg viewBox="0 0 240 300" width="230" role="img" aria-label="Glass of water, {label}">
  <defs>
    <clipPath id="cup"><path d="M64 60 L176 60 L162 262 Q161 272 150 272 L90 272 Q79 272 78 262 Z"/></clipPath>
    <linearGradient id="sheen" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".25" stop-color="#fff" stop-opacity="0"/></linearGradient>
  </defs>
  <g clip-path="url(#cup)">
    <rect x="40" y="96" width="170" height="190" fill="{water}"/>
    <g class="wave"><path d="M-60 96 q15 -9 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 V120 H-60 Z" fill="{water}"/></g>
    {specks}
    <rect x="64" y="60" width="112" height="212" fill="url(#sheen)"/>
  </g>
  <path d="M64 60 L176 60 L162 262 Q161 272 150 272 L90 272 Q79 272 78 262 Z" fill="none" stroke="{INK}" stroke-width="3.5" stroke-linejoin="round"/>
  <rect x="104" y="14" width="32" height="32" rx="16" fill="{badge}"/>
  <text x="120" y="36" text-anchor="middle" font-size="16" fill="#fff" font-family="Figtree" font-weight="700">{'✓' if p_potable >= .5 else '!'}</text>
</svg>
<div style="font-family:'Bricolage Grotesque';font-weight:700;font-size:1.15rem;color:{badge};">{label}</div>
<div style="color:#58727F;font-size:.9rem;margin-bottom:6px;">{p_potable*100:.0f}% confidence the water is potable</div>
</div>
"""


def gauge(p):
    _, colr, _ = tone(p)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=p * 100,
            number={"suffix": "%", "font": {"family": "Bricolage Grotesque", "size": 46, "color": INK}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": INK},
                "bar": {"color": colr, "thickness": 0.32},
                "bgcolor": "#F4F8F6",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 30], "color": "#D8EDE5"},
                    {"range": [30, 60], "color": "#F3E8C6"},
                    {"range": [60, 100], "color": "#F6D3CA"},
                ],
            },
        )
    )
    fig.update_layout(height=230, margin=dict(l=20, r=20, t=20, b=0), paper_bgcolor="rgba(0,0,0,0)")
    return fig


# ----------------------------------------------------------------------------
# State + presets
# ----------------------------------------------------------------------------
DEFAULTS = PRESETS["Clear spring"]


def apply_preset(name):
    p = PRESETS[name]
    st.session_state.update(cmin=p["cmin"], cmax=p["cmax"], turb=p["turb"])
    for k, v in zip(SYMPTOMS, p["sym"]):
        st.session_state[f"sym_{k}"] = v


if "cmin" not in st.session_state:
    apply_preset("Clear spring")


def sample_row():
    """Pull a real row from the dataset to try out (converted back to conductivity units)."""
    w = DATA.get("water")
    if w is None:
        return
    r = w.sample(1).iloc[0]
    st.session_state.cmax = int(min(np.expm1(r.TDS_estimated) / 0.64, 5000))
    st.session_state.cmin = int(min(np.expm1(r.TDS_estimated_min) / 0.64, st.session_state.cmax))
    st.session_state.turb = int(min(r.Turbidity_synthetic, 100))


# ----------------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------------
tab_check, tab_map, tab_batch, tab_lab, tab_about = st.tabs(
    ["Check a sample", "Risk map", "Batch scan", "Data lab", "How it works"]
)

# ============================== CHECK =======================================
with tab_check:
    st.caption("Start from a scenario, or enter your own readings.")
    pc = st.columns(len(PRESETS) + 1)
    for c, name in zip(pc, PRESETS):
        c.button(name, on_click=apply_preset, args=(name,), width="stretch")
    pc[-1].button("🎲 Random real sample", on_click=sample_row, width="stretch")

    left, right = st.columns([1.05, 1], gap="large")

    with left:
        st.markdown(
            '<div class="stage"><div class="num">1</div><div><h4>The water</h4>'
            "<small>Readings from the sampling point</small></div></div>",
            unsafe_allow_html=True,
        )
        cmax = st.slider("Highest conductivity (µS/cm)", 0, 5000, key="cmax", help="Max Conductivity. Converted to TDS (×0.64).")
        cmin = st.slider("Lowest conductivity (µS/cm)", 0, 5000, key="cmin")
        if cmin > cmax:
            st.warning("Lowest conductivity is above the highest, so the two were swapped for the model.")
            cmin, cmax = cmax, cmin
        turb = st.slider("Turbidity (NTU)", 0, 100, key="turb", help="How cloudy the water looks.")
        st.markdown(
            f'<div class="pipe">≈ {cmax*0.64:,.0f} mg/L dissolved solids at the peak, {cmin*0.64:,.0f} mg/L at the low</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="stage"><div class="num">2</div><div><h4>The people</h4>'
            "<small>How bad is each symptom among reported cases?</small></div></div>",
            unsafe_allow_html=True,
        )
        sym = []
        for k, emoji in SYMPTOMS.items():
            sym.append(
                st.select_slider(
                    f"{emoji} {k.replace('_', ' ')}", options=[0, 1, 2, 3], key=f"sym_{k}",
                    format_func=lambda i: SEVERITY[i],
                )
            )

    p_pot, potable, p_out = (a[0] for a in run_pipeline(cmin, cmax, turb, sym))
    label, colr, advice = tone(p_out)

    with right:
        g1, g2 = st.columns([0.9, 1.25])
        with g1:
            st.markdown(glass_svg(turb, cmax, p_pot), unsafe_allow_html=True)
        with g2:
            st.plotly_chart(gauge(p_out), width="stretch", config={"displayModeBar": False})
            st.markdown(
                f'<div style="text-align:center;margin-top:-14px;color:#58727F;">chance of an outbreak</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div class="verdict" style="background:{colr};"><h2>{label}</h2><p>{advice}</p></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        m1, m2, m3 = st.columns(3)
        m1.metric("Stage 1: water", "Potable" if potable == 1 else "Not potable", f"{p_pot*100:.0f}% sure", delta_color="off")
        m2.metric("Symptom load", f"{sum(sym)} / 15")
        m3.metric("Stage 2: outbreak", f"{p_out*100:.0f}%")

        # what-if: what would clean water or no symptoms do?
        _, _, p_clean = run_pipeline(30, 100, 8, sym)
        _, _, p_nosym = run_pipeline(cmin, cmax, turb, [0] * 5)
        st.markdown("**What would change the picture?**")
        st.write(
            f"- With the same symptoms but a clean sample, risk would be **{p_clean[0]*100:.0f}%**.\n"
            f"- With this water but no symptoms, risk would be **{p_nosym[0]*100:.0f}%**."
        )

# ============================== RISK MAP ====================================
with tab_map:
    st.subheader("Where does the water tip into 'not drinkable'?")
    st.caption(
        "Sweeps conductivity and turbidity with your lowest-conductivity setting and symptom levels held fixed. "
        "The potability model learned a strict boundary from the dataset, so the safe zone is small."
    )
    view = st.radio("Show", ["Chance the water is potable", "Chance of an outbreak"], horizontal=True)
    cs = np.linspace(10, 600, 60)
    ts = np.linspace(0, 100, 60)
    CC, TT = np.meshgrid(cs, ts)
    pp, _, po = run_pipeline(np.minimum(cmin, CC.ravel()), CC.ravel(), TT.ravel(), sym)
    Z = (pp if view.startswith("Chance the water") else po).reshape(CC.shape) * 100
    scale = [[0, "#2E8B6A"], [0.5, "#F2E3A9"], [1, "#E2553A"]] if "outbreak" in view else [[0, "#E2553A"], [0.5, "#F2E3A9"], [1, "#2E8B6A"]]
    fig = go.Figure(go.Heatmap(x=cs, y=ts, z=Z, colorscale=scale, zmin=0, zmax=100, colorbar=dict(title="%")))
    fig.add_trace(go.Scatter(x=[cmax], y=[turb], mode="markers+text", text=["your sample"], textposition="top right",
                             marker=dict(size=14, color=INK, line=dict(color="white", width=2)), showlegend=False))
    fig.update_layout(height=520, xaxis_title="Highest conductivity (µS/cm)", yaxis_title="Turbidity (NTU)",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=10, b=10),
                      font=dict(family="Figtree", color=INK))
    st.plotly_chart(fig, width="stretch")

# ============================== BATCH =======================================
with tab_batch:
    st.subheader("Scan many sites at once")
    st.caption("Upload a CSV with one row per site. Download the template to see the columns.")
    tmpl = pd.DataFrame(
        {"site": ["Spring A", "Pond B", "Canal C"], "min_conductivity": [30, 90, 400], "max_conductivity": [100, 420, 2400],
         "turbidity": [8, 62, 35], **{k: v for k, v in zip(SYMPTOMS, [[0, 1, 2], [0, 1, 1], [0, 1, 2], [0, 2, 2], [0, 2, 3]])}}
    )
    st.download_button("Download template", tmpl.to_csv(index=False), "tidewatch_template.csv", "text/csv")
    up = st.file_uploader("Your CSV", type="csv")
    df_in = pd.read_csv(up) if up else tmpl
    if not up:
        st.info("Showing the template as an example. Upload your own file to replace it.")
    need = ["min_conductivity", "max_conductivity", "turbidity", *SYMPTOMS]
    miss = [c for c in need if c not in df_in.columns]
    if miss:
        st.error(f"Missing columns: {', '.join(miss)}")
    else:
        lo = np.minimum(df_in.min_conductivity, df_in.max_conductivity)
        hi = np.maximum(df_in.min_conductivity, df_in.max_conductivity)
        pp, pot, po = run_pipeline(lo.values, hi.values, df_in.turbidity.values, [df_in[k].values for k in SYMPTOMS])
        res = df_in.copy()
        res["potable"] = np.where(pot == 1, "Potable", "Not potable")
        res["outbreak_chance_%"] = (po * 100).round(0)
        res["status"] = [tone(p)[0] for p in po]
        st.dataframe(
            res.style.background_gradient(subset=["outbreak_chance_%"], cmap="RdYlGn_r", vmin=0, vmax=100),
            width="stretch", hide_index=True,
        )
        st.download_button("Download results", res.to_csv(index=False), "tidewatch_results.csv", "text/csv")

# ============================== DATA LAB ====================================
with tab_lab:
    st.subheader("The data behind the models")
    w, s = DATA.get("water"), DATA.get("sym")
    if w is None or s is None:
        st.info("Put the CSV files in a `data/` folder next to `app.py` to see this tab.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Potable vs not, by dissolved solids and turbidity**")
            ws = w.sample(1500, random_state=1)
            fig = go.Figure()
            for val, name, col in [(1, "Potable", KELP), (0, "Not potable", CORAL)]:
                d = ws[ws.Potable == val]
                fig.add_trace(go.Scatter(x=d.TDS_estimated, y=d.Turbidity_synthetic, mode="markers", name=name,
                                         marker=dict(color=col, size=5, opacity=.55)))
            fig.update_layout(height=380, xaxis_title="TDS (log scale)", yaxis_title="Turbidity (NTU)",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fff", margin=dict(l=10, r=10, t=10, b=10),
                              font=dict(family="Figtree", color=INK))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.markdown("**Average symptom severity: outbreak vs no outbreak**")
            m = s.groupby("Outbreak")[list(SYMPTOMS)].mean().T
            fig = go.Figure()
            fig.add_bar(x=m.index.str.replace("_", " "), y=m[0], name="No outbreak", marker_color=KELP)
            fig.add_bar(x=m.index.str.replace("_", " "), y=m[1], name="Outbreak", marker_color=CORAL)
            fig.update_layout(barmode="group", height=380, yaxis_title="Mean severity (0-3)",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fff", margin=dict(l=10, r=10, t=10, b=10),
                              font=dict(family="Figtree", color=INK))
            st.plotly_chart(fig, width="stretch")
        k1, k2, k3 = st.columns(3)
        k1.metric("Water samples", f"{len(w):,}")
        k2.metric("Share potable", f"{w.Potable.mean()*100:.0f}%")
        k3.metric("Share labelled outbreak (symptom set)", f"{s.Outbreak.mean()*100:.0f}%")

        imp = pd.DataFrame({"Feature": potability_model.feature_names_in_, "Importance": potability_model.feature_importances_})
        imp2 = pd.DataFrame({"Feature": outbreak_model.feature_names_in_, "Importance": outbreak_model.feature_importances_})
        c3, c4 = st.columns(2)
        for col, d, t in [(c3, imp, "What the potability model looks at"), (c4, imp2, "What the outbreak model looks at")]:
            with col:
                st.markdown(f"**{t}**")
                d = d.sort_values("Importance")
                fig = go.Figure(go.Bar(x=d.Importance, y=d.Feature.str.replace("_", " "), orientation="h", marker_color=INK))
                fig.update_layout(height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fff",
                                  margin=dict(l=10, r=10, t=10, b=10), font=dict(family="Figtree", color=INK))
                st.plotly_chart(fig, width="stretch")

# ============================== ABOUT =======================================
with tab_about:
    st.subheader("How it works")
    a, b = st.columns(2)
    with a:
        st.markdown(
            """
**Stage 1: is the water drinkable?**
A random forest takes three numbers: peak dissolved solids, lowest dissolved solids and turbidity.
You enter conductivity, and the app converts it the same way the notebook did (TDS = conductivity × 0.64, then `log1p`).

**Stage 2: is an outbreak likely?**
A second random forest takes the five symptom severities (0 to 3) plus the Stage 1 answer
(`Potable_Predicted`) and returns an outbreak probability.

The result bands are *low* under 30%, *keep watching* from 30% to 60%, and *outbreak likely* above 60%.
"""
        )
    with b:
        st.markdown(
            """
**Please read before using this for anything real**
- The potable label was defined as "below the 75th percentile of TDS and turbidity" in the dataset, not by a health standard such as BIS or WHO.
- Turbidity and the symptom data are synthetic (random numbers generated in the notebook), and the symptom outbreak label comes from the water label.
- So the outbreak model largely learns "unsafe water plus symptoms". It is a good demo of the pipeline, not a public-health tool.
- The pickled models were saved with scikit-learn 1.6.1. Pin `scikit-learn==1.6.1` if you see version warnings.
"""
        )
