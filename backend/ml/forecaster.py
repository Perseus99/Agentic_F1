import warnings
import pandas as pd

warnings.filterwarnings("ignore")

ARIMA_MIN_POINTS = 8   # Minimum data points needed for reliable ARIMA
SARIMA_MIN_CYCLES = 2  # Need at least 2 full seasonal cycles to fit SARIMA

# Try to import pmdarima for auto tuning, fall back to statsmodels if not installed
try:
    from pmdarima import auto_arima
    AUTO_ARIMA_AVAILABLE = True
    print("[forecaster] pmdarima available — using Auto ARIMA")
except ImportError:
    from statsmodels.tsa.arima.model import ARIMA
    AUTO_ARIMA_AVAILABLE = False
    print("[forecaster] pmdarima not found — using fixed ARIMA(1,1,1)")


def _series_to_df(series: list, freq: str = "M") -> pd.Series:
    """
    Convert list of {date, value} dicts to a pandas Series.
    freq: 'M' for monthly, 'Q' for quarterly
    """
    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    series_out = df["value"].astype(float)
    series_out.index = pd.DatetimeIndex(series_out.index).to_period(freq)
    return series_out


def _upsample_quarterly_to_monthly(fc: dict, n_months: int) -> dict:
    """
    Linearly interpolate a quarterly forecast to monthly resolution.

    Each quarter boundary is treated as a control point; values between
    consecutive quarters are linearly interpolated. This ensures
    _build_projections always has one data point per month rather than
    running out of quarterly entries and falling back to flat decay.
    """
    q_vals  = [e["value"] for e in fc.get("values", [])            if isinstance(e, dict)]
    q_upper = [e["value"] for e in fc.get("uncertainty_upper", []) if isinstance(e, dict)]
    q_lower = [e["value"] for e in fc.get("uncertainty_lower", []) if isinstance(e, dict)]

    if not q_vals:
        return fc

    def _interp(q_list: list, n: int) -> list:
        monthly = []
        for i, val in enumerate(q_list):
            nxt = q_list[i + 1] if i + 1 < len(q_list) else val
            for step in range(3):
                monthly.append(val + (nxt - val) * step / 3)
        return monthly[:n]

    m_vals  = _interp(q_vals,  n_months)
    m_upper = _interp(q_upper, n_months) if q_upper else m_vals
    m_lower = _interp(q_lower, n_months) if q_lower else m_vals

    return {
        "values":            [{"date": f"M{i+1}", "value": round(v, 4)} for i, v in enumerate(m_vals)],
        "uncertainty_upper": [{"date": f"M{i+1}", "value": round(v, 4)} for i, v in enumerate(m_upper)],
        "uncertainty_lower": [{"date": f"M{i+1}", "value": round(v, 4)} for i, v in enumerate(m_lower)],
    }


def _run_arima(series: pd.Series, horizon: int, series_name: str = "", m: int = 1) -> dict:
    """
    Fit best ARIMA (or SARIMA when m > 1) model and forecast forward.

    Args:
        series:      pandas Series with period index
        horizon:     number of periods to forecast
        series_name: label for log output
        m:           seasonal period — 12 for monthly, 4 for quarterly, 1 = no seasonality

    Returns:
        {
            values: [{date, value}],
            uncertainty_upper: [{date, value}],
            uncertainty_lower: [{date, value}]
        }

    Confidence intervals use alpha=0.05 (95% CI) for honest uncertainty
    representation. Wider bands are more accurate than falsely narrow ones,
    and the uncertainty score in sim_layer rewards tight-but-honest bands.
    """
    empty = {"values": [], "uncertainty_upper": [], "uncertainty_lower": []}

    if len(series) < ARIMA_MIN_POINTS:
        print(f"[forecaster] Insufficient data ({len(series)} points) for {series_name}, skipping.")
        return empty

    # Only enable seasonality when we have enough complete cycles
    use_seasonal = (m > 1) and (len(series) >= m * SARIMA_MIN_CYCLES)
    if m > 1 and not use_seasonal:
        print(f"[forecaster] {series_name} — not enough cycles for SARIMA (m={m}), using non-seasonal")

    try:
        if AUTO_ARIMA_AVAILABLE:
            model = auto_arima(
                series,
                start_p=0, max_p=3,
                start_q=0, max_q=3,
                d=None,
                seasonal=use_seasonal,
                m=m if use_seasonal else 1,
                start_P=0, max_P=1,   # keep SARIMA search space tight
                start_Q=0, max_Q=1,
                D=None,
                information_criterion="aic",
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
            )
            best_order = model.order
            seasonal_order = model.seasonal_order if use_seasonal else None
            if seasonal_order:
                print(f"[forecaster] {series_name} — SARIMA order: {best_order} × {seasonal_order}")
            else:
                print(f"[forecaster] {series_name} — ARIMA order: {best_order}")

            forecast_obj = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.05)
            mean_vals = forecast_obj[0]
            conf_int  = forecast_obj[1]

            last_period  = series.index[-1]
            future_periods = [last_period + i + 1 for i in range(horizon)]

            values = [{"date": str(p), "value": round(float(v), 4)} for p, v in zip(future_periods, mean_vals)]
            upper  = [{"date": str(p), "value": round(float(v), 4)} for p, v in zip(future_periods, conf_int[:, 1])]
            lower  = [{"date": str(p), "value": round(float(v), 4)} for p, v in zip(future_periods, conf_int[:, 0])]

        else:
            # Fallback — fixed ARIMA(1,1,1), no seasonality
            from statsmodels.tsa.arima.model import ARIMA as _ARIMA
            model = _ARIMA(series, order=(1, 1, 1))
            fit   = model.fit()
            forecast = fit.get_forecast(steps=horizon)

            mean = forecast.predicted_mean
            conf = forecast.conf_int(alpha=0.05)

            values = [{"date": str(d), "value": round(float(v), 4)} for d, v in mean.items()]
            upper  = [{"date": str(d), "value": round(float(v), 4)} for d, v in conf.iloc[:, 1].items()]
            lower  = [{"date": str(d), "value": round(float(v), 4)} for d, v in conf.iloc[:, 0].items()]

        return {"values": values, "uncertainty_upper": upper, "uncertainty_lower": lower}

    except Exception as e:
        print(f"[forecaster] ARIMA failed for {series_name}: {e} — returning empty forecast")
        return empty


def run_forecasts(raw_data: dict, horizon: int) -> dict:
    """
    Run Auto ARIMA / SARIMA on all economic time series from fetched data.
    Quarterly series (GDP, sector spending) are upsampled to monthly resolution
    so _build_projections always has one data point per month.

    Args:
        raw_data: output from fetcher.fetch_all()
        horizon:  number of months to forecast forward

    Returns:
        dict of forecasts matching MS schema forecasts block.
        GDP and sector_spending forecasts are monthly-upsampled even though
        the underlying data is quarterly.
    """
    print(f"[forecaster] Running ARIMA/SARIMA forecasts for {horizon} months...")

    fred = raw_data.get("fred", {})
    bls  = raw_data.get("bls", {})
    bea  = raw_data.get("bea", {})

    empty     = {"values": [], "uncertainty_upper": [], "uncertainty_lower": []}
    forecasts = {}

    # ── Monthly series (m=12 for SARIMA) ─────────────────────────────────────

    if fred.get("cpi"):
        print("[forecaster] Forecasting CPI (SARIMA m=12)...")
        forecasts["cpi_forecast"] = _run_arima(
            _series_to_df(fred["cpi"], freq="M"), horizon, "CPI", m=12
        )
    else:
        forecasts["cpi_forecast"] = empty

    if fred.get("interest_rate"):
        print("[forecaster] Forecasting interest rate (SARIMA m=12)...")
        forecasts["interest_rate_forecast"] = _run_arima(
            _series_to_df(fred["interest_rate"], freq="M"), horizon, "Interest Rate", m=12
        )
    else:
        forecasts["interest_rate_forecast"] = empty

    if bls.get("unemployment"):
        print("[forecaster] Forecasting unemployment (SARIMA m=12)...")
        forecasts["unemployment_forecast"] = _run_arima(
            _series_to_df(bls["unemployment"], freq="M"), horizon, "Unemployment", m=12
        )
    else:
        forecasts["unemployment_forecast"] = empty

    # ── Quarterly series — forecast at quarterly frequency, upsample to monthly ──

    if fred.get("gdp"):
        print("[forecaster] Forecasting GDP (SARIMA m=4, quarterly → monthly)...")
        gdp_horizon_q = max(1, -(-horizon // 3))  # ceiling division: months → quarters
        gdp_fc_q = _run_arima(
            _series_to_df(fred["gdp"], freq="Q"), gdp_horizon_q, "GDP", m=4
        )
        forecasts["gdp_forecast"] = _upsample_quarterly_to_monthly(gdp_fc_q, horizon)
    else:
        forecasts["gdp_forecast"] = empty

    bea_raw = bea.get("sector_consumer_spending", [])
    try:
        sector_spending_series = sorted([
            {
                "date": f"{r['TimePeriod'][:4]}-{str((int(r['TimePeriod'][5]) - 1) * 3 + 1).zfill(2)}-01",
                "value": float(r["DataValue"].replace(",", ""))
            }
            for r in bea_raw
            if r.get("LineNumber") == "1" and r.get("DataValue", "").replace(",", "").isdigit()
        ], key=lambda x: x["date"])
    except Exception:
        sector_spending_series = []

    if sector_spending_series:
        print("[forecaster] Forecasting sector spending (SARIMA m=4, quarterly → monthly)...")
        spending_horizon_q = max(1, -(-horizon // 3))
        spending_fc_q = _run_arima(
            _series_to_df(sector_spending_series, freq="Q"),
            spending_horizon_q,
            "Sector Spending",
            m=4,
        )
        forecasts["sector_spending_forecast"] = _upsample_quarterly_to_monthly(spending_fc_q, horizon)
    else:
        print("[forecaster] No BEA sector spending data — skipping sector spending forecast.")
        forecasts["sector_spending_forecast"] = empty

    print("[forecaster] All forecasts complete.")
    return forecasts
