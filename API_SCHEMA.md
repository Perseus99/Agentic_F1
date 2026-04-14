# TwinTrack — API Schema Reference

Backend runs on `http://127.0.0.1:8765` by default.  
Frontend reads `VITE_API_BASE` env var (falls back to the above).

---

## Endpoints

### `GET /api/health`
No request body.

**Response**
```json
{ "ok": true, "service": "twintrack-sim" }
```

---

### `GET /api/enrollments`
Returns all registered businesses (for populating the simulation form dropdown).

**Response**
```json
{
  "ok": true,
  "items": [
    {
      "business_id": "1",
      "business_name": "Riverside Oven Co.",
      "date": "2026-04-14",
      "file": "backend/data/base/input_newbusiness_2026-04-14.json"
    }
  ]
}
```

---

### `POST /api/save-twin-layer`
Register a new business. Backend assigns `business_id` — do not generate one on the frontend.

**Request**
```json
{
  "twin_layer": {
    "meta": {
      "business_id": "",
      "business_name": "Riverside Oven Co.",
      "date": "2026-04-14",
      "type": "Bakery / baked goods retail",
      "use_case": null
    },
    "business_profile": {
      "business_type": "Bakery / baked goods retail",
      "location": { "city": "Dallas", "state": "TX" },
      "established": "",
      "business_structure": ""
    },
    "revenue": {
      "total_annual": 420000,
      "channels": [{ "name": "Primary", "percentage": 100 }]
    },
    "costs": {
      "monthly_rent": 3500,
      "monthly_supplies": 4000,
      "monthly_utilities": 600,
      "loan": {
        "original_amount": 0,
        "remaining_balance": 0,
        "monthly_repayment": 800
      }
    },
    "staffing": {
      "total_employees": 8,
      "monthly_wage_bill": 12000
    },
    "products": [
      {
        "category": "Pastries & coffee",
        "price_range": { "min": 3, "max": 18 }
      }
    ],
    "cash": {
      "current_balance": 25000
    },
    "computed": {
      "cogs_percentage": 0,
      "gross_profit": 0,
      "net_income": 0,
      "break_even_monthly": 0,
      "total_operating_expenses": 20900,
      "prime_cost_ratio": 0
    }
  }
}
```

**Response (200)**
```json
{
  "ok": true,
  "saved_to": "backend/data/base/input_newbusiness_2026-04-14.json",
  "result": {
    "twin_layer": { "meta": { "business_id": "1", "..." : "..." } },
    "sim": null,
    "ip1": {
      "business_name": "Riverside Oven Co.",
      "monthly_revenue": 35000.00,
      "monthly_costs": 20900.00,
      "monthly_fixed_costs": 4900.00,
      "monthly_variable_costs": 16000.00,
      "monthly_cogs": 16000.00,
      "monthly_footfall": 1127.0,
      "avg_price_point": 31.06,
      "employee_count": 8,
      "naics_code": "",
      "msa_code": "19100"
    },
    "ip2": null,
    "output": null
  }
}
```

**Response (400)** — missing `twin_layer.meta`
```json
{ "error": "twin_layer with meta is required" }
```

> **Frontend note:** After a successful enrollment, store `result.twin_layer.meta.business_id` and `result.twin_layer` in `sessionStorage` — the current UI does this under keys `twintrack_business_id` and `twintrack_twin_layer_json`.

---

### `POST /api/update-twin-layer`
Update financials for an already-enrolled business. Creates a new versioned file; does not overwrite the original.

**Request**
```json
{
  "business_id": "1",
  "effective_date": "2026-04-14",
  "delta_notes": "Q2 cost review",
  "optional_metrics": {
    "revenue_current": 38000,
    "costs_current": 22000
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `business_id` | Yes | String or number — matched case-insensitively |
| `effective_date` | No | ISO date string; defaults to today |
| `delta_notes` | No | Free-text note stored in `meta.update_notes` |
| `optional_metrics.revenue_current` | No | Monthly figure — backend multiplies by 12 for annual |
| `optional_metrics.costs_current` | No | Monthly total — backend proportionally scales line items |

**Response (200)**
```json
{
  "ok": true,
  "saved_to": "backend/data/base/input_newbusiness_1_v2_2026-04-14.json",
  "version": 2,
  "result": {
    "twin_layer": { "..." : "..." },
    "sim": null,
    "ip1": { "..." : "..." },
    "ip2": null,
    "output": null
  }
}
```

**Response (404)** — business not found
```json
{
  "error": "No enrolled business found for business_id '99'",
  "available_business_ids": ["1", "2"]
}
```

---

### `POST /api/simulate`
Run a what-if simulation. Returns OP1 (control baseline) and OP2 (experiment outcome) plus an LLM-generated recommendation.

**Request**
```json
{
  "business_id": "1",
  "sim": {
    "useCase": "pricing",
    "label": "Q3 price increase",
    "nlDescription": "We want to raise pastry prices by 15% to cover rising flour costs.",

    "priceChangePct": 10,
    "priceScope": "all",

    "marketingBudgetPct": null,
    "audienceShift": null,

    "franchiseFee": null,
    "royaltyPct": null,
    "newLocations": null
  }
}
```

`useCase` is one of: `"pricing"` | `"audience"` | `"franchising"`.  
Only include the fields relevant to the selected use case — others can be `null` or omitted.

| Use case | Relevant sim fields |
|---|---|
| `pricing` | `priceChangePct`, `priceScope` |
| `audience` | `audienceShift` (`"18_34"` / `"35_54"` / `"55_plus"`), `marketingBudgetPct` |
| `franchising` | `newLocations`, `franchiseFee`, `royaltyPct` |

**Response (200)**
```json
{
  "ok": true,
  "result": {
    "use_case": "pricing",
    "op1": {
      "financials": {
        "revenue": 35000.00,
        "profit": 14100.00,
        "margin": 0.4029,
        "break_even": 20900.00,
        "cogs": 20900.00,
        "avg_ticket": 31.06,
        "footfall": 1127
      },
      "projections": {
        "revenue_6m": [
          { "month": 1, "value": 35000.00 },
          { "month": 2, "value": 35280.00 },
          { "month": 3, "value": 35560.00 },
          { "month": 4, "value": 35840.00 },
          { "month": 5, "value": 36130.00 },
          { "month": 6, "value": 36420.00 }
        ],
        "footfall_6m": [
          { "month": 1, "value": 1127 },
          { "month": 2, "value": 1136 }
        ],
        "market_growth": 0.0230
      },
      "risk": {
        "confidence_score": 0.72,
        "sentiment_score": 0.15,
        "flags": ["Rising CPI may dampen willingness to pay"]
      },
      "delta": {}
    },
    "op2": {
      "financials": {
        "revenue": 37485.00,
        "profit": 15700.00,
        "margin": 0.4189,
        "break_even": 21785.00,
        "cogs": 21785.00,
        "avg_ticket": 34.17,
        "footfall": 1097,
        "break_even_months": 24.5
      },
      "projections": {
        "revenue_6m": [ { "month": 1, "value": 37485.00 }, "..." ],
        "footfall_6m": [ { "month": 1, "value": 1097 }, "..." ],
        "market_growth": 0.0230
      },
      "risk": {
        "confidence_score": 0.72,
        "sentiment_score": 0.15,
        "flags": []
      },
      "delta": {
        "revenue_delta": 2485.00,
        "profit_delta": 1600.00,
        "margin_delta": 0.0160
      }
    },
    "recommendation": "Based on the simulation, raising prices by 10% is projected to increase monthly revenue by $2,485 (+7.1%) while footfall decreases moderately (-2.7%). The confidence score of 72% reflects stable GDP growth and moderate CPI pressure. This is a favorable trade-off given your current margin structure."
  }
}
```

> **Note:** `break_even_months` is only present in `op2.financials` for the `franchising` use case.  
> `op1.delta` is always `{}`. `op2.delta` always has `revenue_delta`, `profit_delta`, `margin_delta`.

---

## Field type reference

| Field | Type | Notes |
|---|---|---|
| `business_id` | `string` | Assigned by backend; always stored as string |
| `monthly_revenue` | `number` | Dollars, 2 decimal places |
| `margin` | `number` | Decimal (e.g. `0.40` = 40%) |
| `confidence_score` | `number` | 0–1 float |
| `sentiment_score` | `number` | −1 to +1 float |
| `flags` | `{headline: string, relevance: string, impact: "positive"\|"negative"\|"neutral"}[]` | May be empty array |
| `revenue_6m` / `footfall_6m` | `{month: number, value: number}[]` | Always 6 entries |
| `market_growth` | `number` | Decimal (e.g. `0.023` = 2.3% annual) |
| `recommendation` | `string` | Plain English, 2–5 sentences |

---

## Error response shape (all endpoints)

```json
{ "error": "<message>", "detail": "<optional extra info>" }
```

HTTP status codes used: `200`, `400`, `404`, `500`.

---

## Known gaps / items to coordinate

1. **`royaltyPct` and `priceScope`** are collected in the UI but are not consumed by the backend simulation engine. They are silently ignored for now. Do not build UI logic that depends on them producing a different result.

2. **`nlDescription` hint text** (`TwinTrack.jsx` step 3 description) still mentions "Claude Haiku". The backend now uses local Ollama (`qwen2.5:7b`). Update the hint text to avoid confusion during demo.

3. **`timelineMonths`** exists in the frontend sim state but is never included in the API payload. The backend always returns a fixed 6-month projection window.

4. **sessionStorage dependency:** The dashboard screen reads `twintrack_twin_layer_json` from `sessionStorage` to show business name/type/location. If the user navigates directly to the simulate screen without going through enrollment first, `bizForDash` will show fallback values. Keep this in mind if redesigning the navigation flow.
