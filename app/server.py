"""
NeerNirikshak — Flask Backend
IoT Water Quality Monitoring & Outbreak Detection System

Two-stage ML pipeline:
  1) Water sample (TDS min/max, turbidity)  → potability model  → Potable_Predicted
  2) Symptoms (0-3) + Potable_Predicted     → outbreak model    → outbreak probability

Data sources:
  - ESP32 sensors → Firebase Realtime Database (TDS, turbidity)
  - Google Forms  → Firestore (symptom reports)

Run:  python server.py
"""

import json
import sys
import warnings

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

warnings.filterwarnings("ignore")

# ─── Firebase Admin SDK (optional — graceful fallback to demo mode) ──────────
firebase_admin = None
credentials = None
rtdb = None
firestore = None
HAS_FIREBASE_SDK = False

try:
    import firebase_admin
    from firebase_admin import credentials, db as rtdb, firestore
    HAS_FIREBASE_SDK = True
except (ImportError, Exception):
    HAS_FIREBASE_SDK = False

HERE = Path(__file__).parent

# ─── Flask App ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# ─── Constants ───────────────────────────────────────────────────────────────
SYMPTOM_KEYS = ["Nausea", "Fever", "Dehydration", "Abdominal_Cramps", "Diarrhoea"]
SEVERITY_LABELS = ["None", "Mild", "Moderate", "Severe"]
LOCATIONS = [
    "Ward 1", "Ward 2", "Ward 3", "Ward 4", "Ward 5",
    "Village A", "Village B", "Town Center", "Riverside",
    "Market Area", "School Zone", "Hospital Area"
]

# ─── Load ML Models ─────────────────────────────────────────────────────────
potability_model = None
outbreak_model = None


def load_models():
    """Load the pre-trained scikit-learn models from disk."""
    global potability_model, outbreak_model
    model_dir = HERE / "models"
    pm_path = model_dir / "water_potability_model.pkl"
    om_path = model_dir / "outbreak_prediction_model.pkl"

    if pm_path.exists() and om_path.exists():
        try:
            potability_model = joblib.load(pm_path)
            outbreak_model = joblib.load(om_path)
            print("  ✓ ML models loaded successfully")
        except Exception as e:
            print(f"  ⚠ Failed to load model files: {e}")
            potability_model = None
            outbreak_model = None
    else:
        print("  ✗ Model .pkl files not found in models/ directory!")


load_models()

# ─── Load CSV Datasets ──────────────────────────────────────────────────────
datasets = {}


def load_datasets():
    """Load all CSV datasets from the data/ directory."""
    global datasets
    data_dir = HERE / "data"
    for key, filename in [
        ("water", "water_potability_dataset.csv"),
        ("symptoms", "outbreak_symptoms_dataset.csv"),
        ("waterborne", "waterborne_symptoms_dataset.csv"),
    ]:
        path = data_dir / filename
        if path.exists():
            try:
                datasets[key] = pd.read_csv(path)
            except Exception as e:
                print(f"  ⚠ Failed to load {filename}: {e}")
    print(f"  ✓ Loaded {len(datasets)} datasets: {list(datasets.keys())}")


load_datasets()

# ─── Firebase Initialization ────────────────────────────────────────────────
firebase_mode = "demo"
firestore_client = None


def init_firebase():
    """Try to connect to Firebase. Falls back to demo mode if unavailable."""
    global firebase_mode, firestore_client

    if not HAS_FIREBASE_SDK:
        print("  ⚠ firebase-admin package not installed — demo mode")
        return

    cred_path = HERE / "firebase_service_account.json"
    if not cred_path.exists():
        print("  ⚠ firebase_service_account.json not found — demo mode")
        return

    try:
        raw = json.loads(cred_path.read_text())
        # Skip placeholder config
        if raw.get("project_id", "").startswith("YOUR"):
            print("  ⚠ Firebase config is still placeholder — demo mode")
            return

        db_url = raw.pop("databaseURL", None) or "https://neernirikshak-default-rtdb.asia-southeast1.firebasedatabase.app"
        cred = credentials.Certificate(raw)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})
        firestore_client = firestore.client()
        firebase_mode = "live"
        print(f"  ✓ Firebase connected in LIVE mode (RTDB: {db_url})")
    except Exception as e:
        print(f"  ⚠ Firebase init failed: {e} — demo mode")


print("\n╔══════════════════════════════════════════════╗")
print("║       NeerNirikshak — Starting Server        ║")
print("╚══════════════════════════════════════════════╝")
init_firebase()


# ═══════════════════════════════════════════════════════════════════════════════
# ML PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def predict(tds_min_conductivity, tds_max_conductivity, turbidity, symptoms):
    """
    Two-stage ML prediction pipeline (mirrors the Jupyter notebook logic).

    Stage 1: Conductivity → TDS → log1p → potability random forest
    Stage 2: Symptoms (0-3) + potable prediction → outbreak random forest

    Returns a dict with potability and outbreak results.
    """
    try:
        cmin = float(tds_min_conductivity)
        cmax = float(tds_max_conductivity)
        turb = float(turbidity)
    except (ValueError, TypeError):
        cmin, cmax, turb = 30.0, 100.0, 8.0

    # Swap if needed
    if cmin > cmax:
        cmin, cmax = cmax, cmin

    # Clean symptoms to 5 non-negative integers (0-3)
    clean_sym = []
    for s in (symptoms or [])[:5]:
        try:
            clean_sym.append(min(max(int(s), 0), 3))
        except (ValueError, TypeError):
            clean_sym.append(0)
    while len(clean_sym) < 5:
        clean_sym.append(0)

    # Stage 1: Water potability
    if potability_model is not None:
        water_features = pd.DataFrame({
            "TDS_estimated": [np.log1p(cmax * 0.64)],
            "TDS_estimated_min": [np.log1p(cmin * 0.64)],
            "Turbidity_synthetic": [turb],
        })
        potable_prob = float(potability_model.predict_proba(water_features)[0, 1])
        potable_pred = int(potability_model.predict(water_features)[0])
    else:
        is_pot = (cmax * 0.64 <= 300.0) and (turb <= 5.0)
        potable_pred = 1 if is_pot else 0
        potable_prob = 0.95 if is_pot else 0.10

    # Stage 2: Outbreak prediction
    if outbreak_model is not None:
        sym_frame = pd.DataFrame({
            k: [int(v)] for k, v in zip(SYMPTOM_KEYS, clean_sym)
        })
        sym_frame["Potable_Predicted"] = potable_pred
        feature_cols = list(outbreak_model.feature_names_in_)
        outbreak_prob = float(
            outbreak_model.predict_proba(sym_frame[feature_cols])[0, 1]
        )
    else:
        sym_load = sum(clean_sym)
        base = sym_load / 15.0
        if potable_pred == 0:
            base = min(base + 0.25, 1.0)
        outbreak_prob = base

    # Risk classification
    if outbreak_prob < 0.30:
        risk_level, risk_color = "Low", "#00d4aa"
        advice = "No sign of an outbreak from this sample and symptoms."
    elif outbreak_prob < 0.60:
        risk_level, risk_color = "Watch", "#ffb830"
        advice = "Mixed signals. Re-test water and monitor reported symptoms."
    else:
        risk_level, risk_color = "High", "#ff5252"
        advice = "Water and symptoms both indicate risk. Alert local health staff."

    symptom_load = sum(clean_sym)

    return {
        "potability": {
            "is_potable": potable_pred == 1,
            "confidence": round(potable_prob * 100, 1),
            "label": "Potable" if potable_pred == 1 else "Not Potable",
        },
        "outbreak": {
            "probability": round(outbreak_prob * 100, 1),
            "risk_level": risk_level,
            "risk_color": risk_color,
            "advice": advice,
        },
        "inputs": {
            "tds_max_conductivity": cmax,
            "tds_min_conductivity": cmin,
            "tds_max_mg_l": round(cmax * 0.64, 1),
            "tds_min_mg_l": round(cmin * 0.64, 1),
            "turbidity": turb,
            "symptoms": {k: int(v) for k, v in zip(SYMPTOM_KEYS, clean_sym)},
            "symptom_load": f"{symptom_load}/15",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO DATA GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# LIVE & DEMO DATA BUFFERS
# ═══════════════════════════════════════════════════════════════════════════════

live_sensor_buffer = []
live_symptom_buffer = []
_last_auto_tick = datetime.now(timezone.utc)


def init_data_buffers():
    """Seed initial sensor and symptom data from datasets."""
    global live_sensor_buffer, live_symptom_buffer
    water_df = datasets.get("water")
    now = datetime.now(timezone.utc)

    if water_df is not None:
        samples = water_df.sample(min(24, len(water_df)), random_state=42)
        for i, (_, row) in enumerate(samples.iterrows()):
            ts = now - timedelta(minutes=(24 - i) * 5)
            tds_max = round(float(min(np.expm1(row.TDS_estimated) / 0.64, 5000)), 1)
            tds_min = round(float(min(np.expm1(row.TDS_estimated_min) / 0.64, 5000)), 1)
            turb = round(float(min(row.Turbidity_synthetic, 100)), 1)

            # Evaluate potability using ML model if loaded
            potable_val = int(row.get("Potable", 0))
            if potability_model is not None:
                feat = pd.DataFrame({
                    "TDS_estimated": [np.log1p(tds_max * 0.64)],
                    "TDS_estimated_min": [np.log1p(tds_min * 0.64)],
                    "Turbidity_synthetic": [turb],
                })
                try:
                    potable_val = int(potability_model.predict(feat)[0])
                except Exception:
                    pass

            live_sensor_buffer.append({
                "tds_max": tds_max,
                "tds_min": tds_min,
                "turbidity": turb,
                "timestamp": ts.isoformat(),
                "device_id": "ESP32_NODE_01",
                "potable": potable_val,
            })

    sym_df = datasets.get("symptoms")
    if sym_df is not None:
        samples = sym_df.sample(min(20, len(sym_df)), random_state=42)
        rng = np.random.default_rng(42)
        for i, (_, row) in enumerate(samples.iterrows()):
            ts = now - timedelta(minutes=(20 - i) * 8)
            live_symptom_buffer.append({
                "nausea": int(row.Nausea),
                "fever": int(row.Fever),
                "dehydration": int(row.Dehydration),
                "abdominal_cramps": int(row.Abdominal_Cramps),
                "diarrhoea": int(row.Diarrhoea),
                "outbreak": int(row.get("Outbreak", 0)),
                "location": LOCATIONS[int(rng.integers(0, len(LOCATIONS)))],
                "timestamp": ts.isoformat(),
            })


init_data_buffers()


def tick_simulated_stream():
    """In demo mode, append a new dynamic live reading every few seconds."""
    global _last_auto_tick
    now = datetime.now(timezone.utc)
    if (now - _last_auto_tick).total_seconds() < 3.0:
        return

    _last_auto_tick = now
    if not live_sensor_buffer:
        return

    last = live_sensor_buffer[-1]
    rng = np.random.default_rng()

    # Dynamic subtle drift to simulate active IoT stream
    drift_tds = float(rng.normal(0, 8.0))
    drift_turb = float(rng.normal(0, 1.2))

    new_tds_max = round(float(np.clip(last["tds_max"] + drift_tds, 40.0, 1500.0)), 1)
    new_tds_min = round(float(np.clip(new_tds_max * rng.uniform(0.15, 0.45), 5.0, new_tds_max)), 1)
    new_turb = round(float(np.clip(last["turbidity"] + drift_turb, 1.0, 95.0)), 1)

    potable_val = 1
    if potability_model is not None:
        feat = pd.DataFrame({
            "TDS_estimated": [np.log1p(new_tds_max * 0.64)],
            "TDS_estimated_min": [np.log1p(new_tds_min * 0.64)],
            "Turbidity_synthetic": [new_turb],
        })
        try:
            potable_val = int(potability_model.predict(feat)[0])
        except Exception:
            pass

    live_sensor_buffer.append({
        "tds_max": new_tds_max,
        "tds_min": new_tds_min,
        "turbidity": new_turb,
        "timestamp": now.isoformat(),
        "device_id": "ESP32_NODE_01",
        "potable": potable_val,
    })

    if len(live_sensor_buffer) > 50:
        live_sensor_buffer.pop(0)

    # Occasionally add a new symptom report
    if rng.random() < 0.25 and datasets.get("symptoms") is not None:
        row = datasets["symptoms"].sample(1).iloc[0]
        live_symptom_buffer.append({
            "nausea": int(row.Nausea),
            "fever": int(row.Fever),
            "dehydration": int(row.Dehydration),
            "abdominal_cramps": int(row.Abdominal_Cramps),
            "diarrhoea": int(row.Diarrhoea),
            "outbreak": int(row.get("Outbreak", 0)),
            "location": LOCATIONS[int(rng.integers(0, len(LOCATIONS)))],
            "timestamp": now.isoformat(),
        })
        if len(live_symptom_buffer) > 50:
            live_symptom_buffer.pop(0)


# ═══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Health check and connection status."""
    return jsonify({
        "success": True,
        "mode": firebase_mode,
        "models_loaded": potability_model is not None and outbreak_model is not None,
        "datasets_loaded": list(datasets.keys()),
        "sensor_count": len(live_sensor_buffer),
        "symptom_count": len(live_symptom_buffer),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def get_live_rtdb_point():
    """Fetch live reading from RTDB (checking /water_monitor/live and /sensors)."""
    if firebase_mode != "live":
        return None
    try:
        # Check /water_monitor/live (ESP32 node)
        live_node = rtdb.reference("/water_monitor/live").get()
        if isinstance(live_node, dict):
            tds_val = float(live_node.get("tds", 0.0))
            turb_val = float(live_node.get("turbidity", 0.0))
            turb_v = float(live_node.get("turb_voltage", 0.0))
            raw_ts = live_node.get("timestamp")

            tds_max = float(live_node.get("tds_max", tds_val))
            tds_min = float(live_node.get("tds_min", tds_val * 0.85 if tds_val > 0 else 0.0))

            # Run ML potability model on live reading
            potable_val = 1
            potable_conf = 100.0
            if potability_model is not None:
                feat = pd.DataFrame({
                    "TDS_estimated": [np.log1p(tds_max * 0.64)],
                    "TDS_estimated_min": [np.log1p(tds_min * 0.64)],
                    "Turbidity_synthetic": [turb_val],
                })
                try:
                    potable_val = int(potability_model.predict(feat)[0])
                    potable_conf = round(float(potability_model.predict_proba(feat)[0, 1]) * 100, 1)
                except Exception:
                    pass

            return {
                "device_id": "ESP32_WATER_MONITOR",
                "tds": round(tds_val, 1),
                "tds_max": round(tds_max, 1),
                "tds_min": round(tds_min, 1),
                "turbidity": round(turb_val, 1),
                "turb_voltage": round(turb_v, 2),
                "status": live_node.get("status", "Safe"),
                "potable": potable_val,
                "confidence": potable_conf,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_timestamp": raw_ts,
            }

        # Fallback to /sensors node
        ref = rtdb.reference("/sensors")
        data = ref.get()
        if data:
            sensors = list(data.values()) if isinstance(data, dict) else list(data)
            sensors = [s for s in sensors if isinstance(s, dict)]
            if sensors:
                return sensors[-1]
    except Exception as e:
        print(f"  ⚠ RTDB fetch error: {e}")
    return None


@app.route("/api/sensor-data", methods=["GET", "POST"])
def api_sensor_data():
    """
    GET: Fetch latest sensor readings from Firebase RTDB (or live buffer).
    POST: Ingest new live reading from ESP32 or external script.
    """
    global live_sensor_buffer

    if request.method == "POST":
        data = request.json or {}
        tds_min = float(data.get("tds_min", 30))
        tds_max = float(data.get("tds_max", 100))
        turb = float(data.get("turbidity", 8))
        dev_id = str(data.get("device_id", "ESP32_IOT"))
        ts = data.get("timestamp") or datetime.now(timezone.utc).isoformat()

        # Run potability ML model
        potable_val = 1
        conf = 100.0
        if potability_model is not None:
            feat = pd.DataFrame({
                "TDS_estimated": [np.log1p(tds_max * 0.64)],
                "TDS_estimated_min": [np.log1p(tds_min * 0.64)],
                "Turbidity_synthetic": [turb],
            })
            potable_val = int(potability_model.predict(feat)[0])
            conf = round(float(potability_model.predict_proba(feat)[0, 1]) * 100, 1)

        reading = {
            "device_id": dev_id,
            "tds": round(tds_max, 1),
            "tds_min": round(tds_min, 1),
            "tds_max": round(tds_max, 1),
            "turbidity": round(turb, 1),
            "potable": potable_val,
            "confidence": conf,
            "timestamp": ts,
        }

        live_sensor_buffer.append(reading)
        if len(live_sensor_buffer) > 50:
            live_sensor_buffer.pop(0)

        # Sync to Firebase RTDB if live
        if firebase_mode == "live":
            try:
                rtdb.reference("/sensors").push(reading)
            except Exception as e:
                print(f"  ⚠ Failed to sync sensor reading to RTDB: {e}")

        return jsonify({"success": True, "data": reading, "mode": firebase_mode})

    # GET request
    if firebase_mode == "live":
        rtdb_point = get_live_rtdb_point()
        if rtdb_point:
            # Check if this point is new compared to buffer
            if not live_sensor_buffer or live_sensor_buffer[-1].get("raw_timestamp") != rtdb_point.get("raw_timestamp"):
                live_sensor_buffer.append(rtdb_point)
                if len(live_sensor_buffer) > 50:
                    live_sensor_buffer.pop(0)
            return jsonify({
                "success": True,
                "data": list(live_sensor_buffer),
                "mode": "live",
                "latest_live": rtdb_point,
            })

    # Fallback to dynamic live stream simulation
    tick_simulated_stream()
    return jsonify({
        "success": True,
        "data": list(live_sensor_buffer),
        "mode": firebase_mode,
    })


def normalize_symptom_doc(raw):
    """Normalize Firestore document (Google Form schema) to standard ML format."""
    if not isinstance(raw, dict):
        return {}

    ts = raw.get("timestamp")
    if hasattr(ts, "isoformat"):
        ts_str = ts.isoformat()
    elif isinstance(ts, str):
        ts_str = ts
    else:
        ts_str = datetime.now(timezone.utc).isoformat()

    # Parse severity label or number
    sev_raw = raw.get("severity", "Moderate")
    sev_map = {"none": 0, "mild": 1, "moderate": 2, "severe": 3}
    default_sev = sev_map.get(str(sev_raw).lower(), 2) if isinstance(sev_raw, str) else int(sev_raw)

    norm = {
        "nausea": int(raw.get("nausea", 0)),
        "fever": int(raw.get("fever", 0)),
        "dehydration": int(raw.get("dehydration", 0)),
        "abdominal_cramps": int(raw.get("abdominal_cramps", raw.get("cramps", 0))),
        "diarrhoea": int(raw.get("diarrhoea", raw.get("diarrhea", 0))),
        "location": str(raw.get("locality") or raw.get("location") or "General Ward"),
        "timestamp": ts_str,
        "age_group": str(raw.get("age_group", "All")),
        "duration": str(raw.get("duration", "Recent")),
    }

    # If Google Form checked symptoms as a list: e.g. ['Abdominal Pain/Cramps', 'Fever']
    sym_list = raw.get("symptoms")
    if isinstance(sym_list, list):
        for s in sym_list:
            sl = str(s).lower()
            if "nausea" in sl or "vomit" in sl:
                norm["nausea"] = default_sev
            if "fever" in sl:
                norm["fever"] = default_sev
            if "dehydrat" in sl:
                norm["dehydration"] = default_sev
            if "abdomin" in sl or "cramp" in sl or "pain" in sl or "stomach" in sl:
                norm["abdominal_cramps"] = default_sev
            if "diarrh" in sl or "loose" in sl:
                norm["diarrhoea"] = default_sev

    return norm


@app.route("/api/symptom-data", methods=["GET", "POST"])
def api_symptom_data():
    """
    GET: Fetch symptom reports from Firestore (or live buffer).
    POST: Ingest new symptom report from Google Form or clinic webhook.
    """
    global live_symptom_buffer

    if request.method == "POST":
        data = request.json or {}
        nausea = int(data.get("nausea", 0))
        fever = int(data.get("fever", 0))
        dehydration = int(data.get("dehydration", 0))
        abdominal_cramps = int(data.get("abdominal_cramps", 0))
        diarrhoea = int(data.get("diarrhoea", 0))
        location = str(data.get("location", "Ward 1"))
        ts = data.get("timestamp") or datetime.now(timezone.utc).isoformat()

        report = {
            "nausea": min(max(nausea, 0), 3),
            "fever": min(max(fever, 0), 3),
            "dehydration": min(max(dehydration, 0), 3),
            "abdominal_cramps": min(max(abdominal_cramps, 0), 3),
            "diarrhoea": min(max(diarrhoea, 0), 3),
            "location": location,
            "timestamp": ts,
        }

        live_symptom_buffer.append(report)
        if len(live_symptom_buffer) > 50:
            live_symptom_buffer.pop(0)

        # Sync to Firestore if live
        if firebase_mode == "live" and firestore_client:
            try:
                firestore_client.collection("symptom_reports").add(report)
            except Exception as e:
                print(f"  ⚠ Failed to sync symptom report to Firestore: {e}")

        return jsonify({"success": True, "data": report, "mode": firebase_mode})

    # GET request
    if firebase_mode == "live" and firestore_client:
        try:
            docs = (
                firestore_client.collection("symptom_reports")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(50)
                .stream()
            )
            symptoms = [normalize_symptom_doc(doc.to_dict()) for doc in docs]
            if symptoms:
                return jsonify({"success": True, "data": symptoms, "mode": "live"})
        except Exception as e:
            print(f"  ⚠ Firestore read error: {e}")

    tick_simulated_stream()
    return jsonify({
        "success": True,
        "data": list(live_symptom_buffer),
        "mode": firebase_mode,
    })


@app.route("/api/predict", methods=["POST"])
def api_predict():
    """Run ML pipeline on manually provided inputs."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    try:
        result = predict(
            data.get("tds_min", 30),
            data.get("tds_max", 100),
            data.get("turbidity", 8),
            [
                data.get("nausea", 0),
                data.get("fever", 0),
                data.get("dehydration", 0),
                data.get("abdominal_cramps", 0),
                data.get("diarrhoea", 0),
            ],
        )
        if result is None:
            return jsonify({"success": False, "error": "Models not loaded"}), 500
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/predict/live")
def api_predict_live():
    """Run the ML pipeline on the latest Firebase/demo data automatically."""
    # Get latest sensor reading
    sensor = None
    if firebase_mode == "live":
        sensor = get_live_rtdb_point()

    if sensor is None:
        tick_simulated_stream()
        sensor = live_sensor_buffer[-1] if live_sensor_buffer else {"tds_min": 30, "tds_max": 100, "turbidity": 8}

    # Get recent symptom reports and average severities
    sym_data = None
    if firebase_mode == "live" and firestore_client:
        try:
            docs = (
                firestore_client.collection("symptom_reports")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(10)
                .stream()
            )
            sym_data = [normalize_symptom_doc(doc.to_dict()) for doc in docs]
        except Exception as e:
            print(f"  ⚠ Firestore prediction read error: {e}")

    if sym_data is None:
        sym_data = live_symptom_buffer[-10:] if live_symptom_buffer else []

    # Average symptom severities from recent reports
    symptoms = [0, 0, 0, 0, 0]
    if sym_data:
        def avg(key):
            vals = [d.get(key, d.get(key.lower(), 0)) for d in sym_data]
            return int(round(np.mean(vals)))
        symptoms = [
            avg("nausea"), avg("fever"), avg("dehydration"),
            avg("abdominal_cramps"), avg("diarrhoea"),
        ]

    result = predict(
        sensor.get("tds_min", 30),
        sensor.get("tds_max", 100),
        sensor.get("turbidity", 8),
        symptoms,
    )

    if result is None:
        return jsonify({"success": False, "error": "Models not loaded"}), 500

    return jsonify({
        "success": True,
        "data": result,
        "mode": firebase_mode,
        "sensor_source": sensor,
        "symptom_reports_used": len(sym_data),
    })


@app.route("/api/dataset-stats")
def api_dataset_stats():
    """Return statistics about the training datasets and model feature importances."""
    stats = {}

    water_df = datasets.get("water")
    if water_df is not None:
        stats["water"] = {
            "total_samples": len(water_df),
            "potable_pct": round(water_df.Potable.mean() * 100, 1),
            "not_potable_pct": round((1 - water_df.Potable.mean()) * 100, 1),
            "avg_tds": round(water_df.TDS_estimated.mean(), 3),
            "avg_turbidity": round(water_df.Turbidity_synthetic.mean(), 1),
        }

    sym_df = datasets.get("symptoms")
    if sym_df is not None:
        stats["symptoms"] = {
            "total_reports": len(sym_df),
            "outbreak_pct": round(sym_df.Outbreak.mean() * 100, 1),
            "no_outbreak_pct": round((1 - sym_df.Outbreak.mean()) * 100, 1),
            "avg_severity": {
                k: round(float(sym_df[k].mean()), 2) for k in SYMPTOM_KEYS
            },
            "outbreak_avg_severity": {
                k: round(float(sym_df[sym_df.Outbreak == 1][k].mean()), 2)
                for k in SYMPTOM_KEYS
            },
            "no_outbreak_avg_severity": {
                k: round(float(sym_df[sym_df.Outbreak == 0][k].mean()), 2)
                for k in SYMPTOM_KEYS
            },
        }

    # Feature importances from trained models
    if potability_model is not None:
        stats["potability_importance"] = [
            {"feature": name.replace("_", " "), "importance": round(float(imp), 4)}
            for name, imp in sorted(
                zip(potability_model.feature_names_in_, potability_model.feature_importances_),
                key=lambda x: x[1], reverse=True,
            )
        ]

    if outbreak_model is not None:
        stats["outbreak_importance"] = [
            {"feature": name.replace("_", " "), "importance": round(float(imp), 4)}
            for name, imp in sorted(
                zip(outbreak_model.feature_names_in_, outbreak_model.feature_importances_),
                key=lambda x: x[1], reverse=True,
            )
        ]

    return jsonify({"success": True, "data": stats})


@app.route("/api/whatif")
def api_whatif():
    """What-if analysis: predict with modified conditions."""
    # Get current latest values (from live RTDB or buffer)
    sensor = get_live_rtdb_point() if firebase_mode == "live" else None
    if sensor is None:
        sensor = live_sensor_buffer[-1] if live_sensor_buffer else {"tds_min": 30, "tds_max": 100, "turbidity": 8}

    demo_sym = None
    if firebase_mode == "live" and firestore_client:
        try:
            docs = firestore_client.collection("symptom_reports").limit(10).stream()
            demo_sym = [normalize_symptom_doc(d.to_dict()) for d in docs]
        except Exception:
            pass
    if not demo_sym:
        demo_sym = live_symptom_buffer[-10:] if live_symptom_buffer else []

    symptoms_avg = [0, 0, 0, 0, 0]
    if demo_sym:
        def avg(key):
            return int(round(np.mean([d.get(key, 0) for d in demo_sym])))
        symptoms_avg = [
            avg("nausea"), avg("fever"), avg("dehydration"),
            avg("abdominal_cramps"), avg("diarrhoea"),
        ]

    cmin = sensor.get("tds_min", 30)
    cmax = sensor.get("tds_max", 100)
    turb = sensor.get("turbidity", 8)

    # Scenario: current
    current = predict(cmin, cmax, turb, symptoms_avg)
    # Scenario: clean water, same symptoms
    clean_water = predict(30, 100, 8, symptoms_avg)
    # Scenario: same water, no symptoms
    no_symptoms = predict(cmin, cmax, turb, [0, 0, 0, 0, 0])
    # Scenario: worst case
    worst_case = predict(cmin, cmax, turb, [3, 3, 3, 3, 3])

    return jsonify({
        "success": True,
        "data": {
            "current": current,
            "clean_water": clean_water,
            "no_symptoms": no_symptoms,
            "worst_case": worst_case,
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n  Mode: {'🟢 LIVE (Firebase)' if firebase_mode == 'live' else '🟡 DEMO (CSV data)'}")
    print("  Dashboard: http://localhost:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
