import os
import sys
import traceback
from datetime import date
from dotenv import load_dotenv

# Ensure backend/ml/ is on sys.path so sibling imports work
# regardless of where the process is launched from
_ML_DIR = os.path.dirname(os.path.abspath(__file__))
if _ML_DIR not in sys.path:
    sys.path.insert(0, _ML_DIR)

load_dotenv()

from context import extract_context, extract_context_from_dict
from fetcher import fetch_all
from forecaster import run_forecasts
from sentiment import run_sentiment
from elasticity import compute_elasticity
from ms_builder import build_ms, write_ms, MS_DIR, OP_DIR
from utils import load_json, validate_ms_schema


def _op1_exists() -> tuple:
    """
    Check if OP1 already exists for today.
    Returns (exists: bool, path: str)
    """
    today = date.today().isoformat()
    path = os.path.join(OP_DIR, f"OP_base_{today}.json")
    return os.path.exists(path), path


def _ms1_exists() -> tuple:
    """
    Check if MS1 already exists for today.
    Returns (exists: bool, path: str)
    """
    today = date.today().isoformat()
    path = os.path.join(MS_DIR, f"MS_base_{today}.json")
    return os.path.exists(path), path


def run(ip_path: str, exp_id: str = None) -> str:
    """
    Main ML layer entry point.

    Args:
        ip_path: path to IP1 or IP2 JSON file
        exp_id:  experiment ID — required when running for IP2

    Returns:
        path to generated MS file
    """
    print(f"\n{'='*50}")
    print(f"[main] TwinTrack ML Layer starting...")
    print(f"[main] IP file: {ip_path}")
    print(f"{'='*50}\n")

    # --- Step 1: Load IP file ---
    try:
        ip = load_json(ip_path)
        ip_type = ip["meta"].get("type", "base")
        business_id = str(ip["meta"].get("business_id") or "unknown")
        use_case = (
            ip.get("simulation_parameters", {}).get("use_case")
            or ip.get("ip2", {}).get("use_case")
            or None
        )
        print(f"[main] IP type: {ip_type}, business_id: {business_id}, use_case: {use_case}")
    except Exception as e:
        print(f"[main] ERROR loading IP file: {e}")
        raise

    # --- Step 1b: OP1 existence check (base case only) ---
    # If OP1 exists for today and this is a base run, MS1 is already valid.
    # Skip full pipeline and return existing MS1.
    if ip_type == "base":
        op1_found, op1_path = _op1_exists()
        ms1_found, ms1_path = _ms1_exists()
        if op1_found and ms1_found:
            print(f"[main] OP1 already exists for today: {op1_path}")
            print(f"[main] Skipping ML pipeline — returning existing MS1: {ms1_path}")
            return ms1_path
        elif op1_found and not ms1_found:
            print(f"[main] OP1 exists but MS1 missing — regenerating MS1.")
        else:
            print(f"[main] No OP1 found for today — running full pipeline.")

    # --- Step 2: Extract business context ---
    try:
        context = extract_context(ip_path)
    except Exception as e:
        print(f"[main] ERROR extracting context: {e}")
        raise

    # --- Step 3: Fetch all API data (with cache) ---
    try:
        raw_data = fetch_all(context)
    except Exception as e:
        print(f"[main] ERROR fetching data: {e}")
        traceback.print_exc()
        raise

    # --- Step 4: Run ARIMA forecasts ---
    try:
        horizon = context.get("forecast_horizon_months", 6)
        forecasts = run_forecasts(raw_data, horizon)
    except Exception as e:
        print(f"[main] ERROR running forecasts: {e}")
        forecasts = {}

    # --- Step 5: Run sentiment analysis ---
    try:
        sentiment = run_sentiment(raw_data, context)
    except Exception as e:
        print(f"[main] ERROR running sentiment: {e}")
        sentiment = {"sentiment_score": 0.0, "flags": []}

    # --- Step 6: Compute elasticity modifiers ---
    try:
        elasticity = compute_elasticity(raw_data)
    except Exception as e:
        print(f"[main] ERROR computing elasticity: {e}")
        elasticity = {
            "price_elasticity":  1.0,
            "labor_elasticity":  1.0,
            "demand_elasticity": 0.0,
            "market_elasticity": 0.5,
        }

    # --- Step 7: Build MS file ---
    try:
        ms = build_ms(
            context=context,
            raw_data=raw_data,
            forecasts=forecasts,
            sentiment=sentiment,
            elasticity=elasticity,
            ip_type=ip_type,
        )
        validate_ms_schema(ms)
    except ValueError as e:
        print(f"[main] ERROR: MS schema validation failed: {e}")
        raise
    except Exception as e:
        print(f"[main] ERROR building MS: {e}")
        raise

    # --- Step 8: Write MS file ---
    try:
        ms_path = write_ms(ms, ip_type, business_id=business_id, use_case=use_case)
    except Exception as e:
        print(f"[main] ERROR writing MS file: {e}")
        raise

    print(f"\n{'='*50}")
    print(f"[main] ML Layer complete.")
    print(f"[main] MS file: {ms_path}")
    print(f"{'='*50}\n")

    return ms_path


def build_market_snapshot(twin: dict) -> dict:
    """
    Build a Market Snapshot (MS) dict from an in-memory twin_layer.
    No file I/O on the input side — returns the MS dict directly.
    Called by orchestrator.run_simulate_pipeline() for the /api/simulate route.

    Args:
        twin: enrolled business twin_layer dict

    Returns:
        MS dict (same schema as run() produces, minus the file path)
    """
    print(f"\n{'='*50}")
    print(f"[main] build_market_snapshot — in-memory path")
    print(f"{'='*50}\n")

    meta        = twin.get("meta") or {}
    business_id = str(meta.get("business_id") or "unknown")
    use_case    = None  # base snapshot, not tied to a specific experiment

    # --- Step 1: Extract context from dict (no file read) ---
    try:
        context = extract_context_from_dict(twin)
    except Exception as e:
        print(f"[main] ERROR extracting context: {e}")
        raise

    # --- Step 2: Fetch all API data (with cache) ---
    try:
        raw_data = fetch_all(context)
    except Exception as e:
        print(f"[main] ERROR fetching data: {e}")
        raise

    # --- Step 3: Run ARIMA forecasts ---
    try:
        horizon   = context.get("forecast_horizon_months", 6)
        forecasts = run_forecasts(raw_data, horizon)
    except Exception as e:
        print(f"[main] ERROR running forecasts: {e}")
        forecasts = {}

    # --- Step 4: Run sentiment analysis ---
    try:
        sentiment = run_sentiment(raw_data, context)
    except Exception as e:
        print(f"[main] ERROR running sentiment: {e}")
        sentiment = {"sentiment_score": 0.0, "flags": []}

    # --- Step 5: Compute elasticity modifiers ---
    try:
        elasticity = compute_elasticity(raw_data)
    except Exception as e:
        print(f"[main] ERROR computing elasticity: {e}")
        elasticity = {
            "price_elasticity":  1.0,
            "labor_elasticity":  1.0,
            "demand_elasticity": 0.0,
            "market_elasticity": 0.5,
        }

    # --- Step 6: Build and validate MS ---
    try:
        ms = build_ms(
            context=context,
            raw_data=raw_data,
            forecasts=forecasts,
            sentiment=sentiment,
            elasticity=elasticity,
            ip_type="base",
        )
        validate_ms_schema(ms)
    except ValueError as e:
        print(f"[main] ERROR: MS schema validation failed: {e}")
        raise
    except Exception as e:
        print(f"[main] ERROR building MS: {e}")
        raise

    # --- Step 7: Write MS to disk for auditing ---
    try:
        write_ms(ms, "base", business_id=business_id, use_case=use_case)
    except Exception as e:
        print(f"[main] WARNING: could not write MS file ({e}) — continuing anyway")

    print(f"\n{'='*50}")
    print(f"[main] build_market_snapshot complete.")
    print(f"{'='*50}\n")

    return ms


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_ip_file> [exp_id]")
        sys.exit(1)

    ip_path = sys.argv[1]
    exp_id  = sys.argv[2] if len(sys.argv) > 2 else None
    ms_path = run(ip_path, exp_id=exp_id)
    print(ms_path)
