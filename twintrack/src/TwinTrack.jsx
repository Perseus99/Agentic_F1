import { useState, useEffect } from "react";
import Dashboard from "./Dashboard.jsx";

/* ─── Data ─────────────────────────────────────────────────────── */
const NAICS_OPTIONS = [
  { value: "722515", label: "Snack & beverage bars" },
  { value: "445291", label: "Bakery / baked goods retail" },
  { value: "448140", label: "Family clothing stores" },
  { value: "812111", label: "Barber / hair / nail services" },
  { value: "722511", label: "Full-service restaurants" },
  { value: "459999", label: "Miscellaneous retail" },
  { value: "541611", label: "Management consulting" },
];

const USE_CASES = [
  {
    id: "franchising",
    title: "Franchise expansion",
    blurb: "Model fees, royalties, and footprint growth.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="4" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="16" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="16" cy="15" r="2.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M6.5 9L13.5 6M6.5 11L13.5 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "pricing",
    title: "Pricing changes",
    blurb: "Shift average price or adjust by category.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M10 3v14M6 7l4-4 4 4M6 13l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: "audience",
    title: "Target audience",
    blurb: "Shift segments, channels, and marketing mix.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="10" cy="10" r="3.5" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="10" cy="10" r="1" fill="currentColor" />
      </svg>
    ),
  },
];

/** sessionStorage key for the Register-business JSON (fed into POST /api/simulate). */
const TWIN_LAYER_STORAGE_KEY = "strategix_twin_layer_json";
/** Last enrolled business UUID — used to autopopulate Run simulation. */
const BUSINESS_ID_STORAGE_KEY = "strategix_business_id";
const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8765").replace(/\/$/, "");

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function createNewEnrollState() {
  return {
    businessId: "",
    businessName: "",
    naics: NAICS_OPTIONS[0].value,
    city: "",
    state: "",
    established: "",
    monthlyRevenue: "",
    monthlyCosts: "",
    headcount: "",
    description: "",
    asOfDate: new Date().toISOString().slice(0, 10),
    businessStructure: "",
    monthlyRent: "",
    monthlySupplies: "",
    monthlyUtilities: "",
    loanOriginal: "",
    loanRemaining: "",
    loanMonthly: "",
    monthlyWageBill: "",
    cashBalance: "",
    channelName: "",
    channelPct: "",
    productCategory: "",
    priceMin: "",
    priceMax: "",
  };
}

/* ─── Styles ────────────────────────────────────────────────────── */
const ACCENT = "#0d9488";        // teal-600
const ACCENT_SOFT = "#ccfbf1";   // teal-100
const ACCENT_DIM = "#0f3a2e";    // dark green
const ACCENT_BG = "rgba(13,148,136,0.14)";
const ACCENT_BORDER = "rgba(13,148,136,0.4)";

const css = {
  root: {
    display: "flex",
    minHeight: "100vh",
    width: "100%",
    fontFamily: "'DM Sans', 'Instrument Sans', 'Segoe UI', system-ui, sans-serif",
    background: "#060c1a",
    color: "#c8d6f0",
    boxSizing: "border-box",
    margin: 0,
    padding: 0,
  },
  sidebar: {
    width: 260,
    minWidth: 260,
    background: "#04091a",
    borderRight: "none",
    display: "flex",
    flexDirection: "column",
    padding: "28px 0 24px",
    position: "sticky",
    top: 0,
    height: "100vh",
    overflowY: "auto",
  },
  sidebarBrand: {
    padding: "0 24px 28px",
    borderBottom: "none",
    marginBottom: 8,
  },
  sidebarTag: {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    color: ACCENT_SOFT,
    margin: "0 0 6px",
  },
  sidebarTitle: {
    fontSize: 22,
    fontWeight: 700,
    color: "#dde8fa",
    margin: 0,
    letterSpacing: "-0.03em",
  },
  sidebarDesc: {
    fontSize: 12,
    lineHeight: 1.6,
    color: "#4a6888",
    margin: "8px 0 0",
  },
  navSection: {
    padding: "16px 16px 0",
  },
  navLabel: {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: "#3d5570",
    padding: "0 8px",
    margin: "0 0 6px",
  },
  navBtn: (active) => ({
    display: "flex",
    alignItems: "center",
    gap: 10,
    width: "100%",
    padding: "10px 12px",
    borderRadius: 10,
    border: "none",
    background: active ? ACCENT_BG : "transparent",
    color: active ? ACCENT_SOFT : "#6080a8",
    fontSize: 13.5,
    fontWeight: active ? 600 : 400,
    cursor: "pointer",
    textAlign: "left",
    transition: "all 0.15s",
    fontFamily: "inherit",
    marginBottom: 2,
  }),
  navDot: (active) => ({
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: active ? ACCENT : "rgba(255,255,255,0.12)",
    flexShrink: 0,
    transition: "background 0.15s",
  }),
  main: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    minWidth: 0,
    overflowY: "auto",
  },
  topbar: {
    padding: "20px 32px 18px",
    borderBottom: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#060c1a",
    position: "sticky",
    top: 0,
    zIndex: 10,
  },
  topbarTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: "#b0c4e8",
    margin: 0,
  },
  topbarSub: {
    fontSize: 12,
    color: "#4a6888",
    margin: "2px 0 0",
  },
  content: {
    padding: "28px 32px 48px",
    flex: 1,
  },
  card: {
    background: "rgba(8,15,32,0.88)",
    border: "none",
    borderRadius: 12,
    padding: "24px 28px",
  },
  fieldLabel: {
    display: "block",
    fontSize: 11.5,
    fontWeight: 600,
    color: "#5a7898",
    marginBottom: 6,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 13px",
    borderRadius: 9,
    border: "1px solid rgba(255,255,255,0.06)",
    background: "rgba(255,255,255,0.02)",
    color: "#c8d6f0",
    fontSize: 14,
    outline: "none",
    fontFamily: "inherit",
    transition: "border-color 0.15s",
  },
  textarea: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 13px",
    borderRadius: 9,
    border: "1px solid rgba(255,255,255,0.06)",
    background: "rgba(255,255,255,0.02)",
    color: "#c8d6f0",
    fontSize: 14,
    outline: "none",
    fontFamily: "inherit",
    resize: "vertical",
    minHeight: 90,
    transition: "border-color 0.15s",
  },
  select: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 13px",
    borderRadius: 9,
    border: "1px solid rgba(255,255,255,0.06)",
    background: "rgba(8,15,32,0.92)",
    color: "#c8d6f0",
    fontSize: 14,
    outline: "none",
    fontFamily: "inherit",
    cursor: "pointer",
  },
  btnPrimary: {
    padding: "11px 20px",
    borderRadius: 9,
    border: "none",
    background: ACCENT,
    color: "#e0eeff",
    fontWeight: 700,
    fontSize: 13.5,
    cursor: "pointer",
    fontFamily: "inherit",
    letterSpacing: "-0.01em",
    transition: "opacity 0.15s",
  },
  btnGhost: {
    padding: "10px 16px",
    borderRadius: 9,
    border: "none",
    background: "rgba(255,255,255,0.03)",
    color: "#6080a8",
    fontSize: 13.5,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  stepDot: (state) => ({
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: state === "done" ? ACCENT : state === "active" ? ACCENT_SOFT : "rgba(255,255,255,0.12)",
    boxShadow: state === "active" ? `0 0 0 3px rgba(13,148,136,0.25)` : "none",
    transition: "all 0.2s",
  }),
  radioCard: (active) => ({
    display: "flex",
    gap: 14,
    alignItems: "flex-start",
    padding: "14px 16px",
    borderRadius: 11,
    border: "none",
    background: active ? "rgba(13,148,136,0.12)" : "rgba(255,255,255,0.02)",
    boxShadow: active ? "inset 0 0 0 1px rgba(13,148,136,0.35)" : "none",
    cursor: "pointer",
    transition: "all 0.15s",
    marginBottom: 8,
  }),
  grid2: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 14,
  },
  sectionDivider: {
    height: 1,
    background: "rgba(255,255,255,0.035)",
    margin: "20px 0",
  },
  successIcon: {
    width: 48,
    height: 48,
    borderRadius: "50%",
    background: "rgba(13,148,136,0.18)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
    border: "1px solid rgba(13,148,136,0.4)",
  },
  metaChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "5px 12px",
    borderRadius: 99,
    background: "rgba(13,148,136,0.12)",
    border: "1px solid rgba(13,148,136,0.25)",
    fontSize: 12.5,
    color: ACCENT_SOFT,
    fontWeight: 500,
    marginRight: 8,
    marginBottom: 8,
  },
  pre: {
    margin: 0,
    padding: "16px 18px",
    borderRadius: 10,
    background: "rgba(0,0,0,0.5)",
    border: "1px solid rgba(255,255,255,0.06)",
    fontSize: 12,
    lineHeight: 1.6,
    overflow: "auto",
    maxHeight: 340,
    color: "#6080a8",
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  },
  errorText: {
    fontSize: 11.5,
    color: "#f87171",
    marginTop: 4,
  },
};

/* ─── Sub-components ────────────────────────────────────────────── */
function Field({ label, error, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={css.fieldLabel}>{label}</label>
      {children}
      {error && <p style={css.errorText}>{error}</p>}
    </div>
  );
}

function StepDots({ current, total }) {
  return (
    <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          style={css.stepDot(i < current - 1 ? "done" : i === current - 1 ? "active" : "idle")}
        />
      ))}
      <span style={{ fontSize: 12, color: "#4a6888", marginLeft: 6 }}>
        Step {current} of {total}
      </span>
    </div>
  );
}

function Topbar({ title, sub }) {
  return (
    <div style={css.topbar}>
      <div>
        <p style={css.topbarTitle}>{title}</p>
        {sub && <p style={css.topbarSub}>{sub}</p>}
      </div>
    </div>
  );
}

/** Parse a numeric form value; empty → default. */
function parseNum(v, defaultValue = 0) {
  if (v === "" || v == null) return defaultValue;
  const n = Number(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : defaultValue;
}

/**
 * Maps the Register business form into the canonical JSON for the next processing layer.
 */
function buildTwinLayerPayload(enroll) {
  const naicsLabel = NAICS_OPTIONS.find((o) => o.value === enroll.naics)?.label ?? "";
  const monthlyRev = parseNum(enroll.monthlyRevenue);
  const monthlyCostTotal = parseNum(enroll.monthlyCosts);
  const rent = parseNum(enroll.monthlyRent);
  const supplies = parseNum(enroll.monthlySupplies);
  const utilities = parseNum(enroll.monthlyUtilities);
  const hasBreakdown = rent > 0 || supplies > 0 || utilities > 0;
  const monthlyRent = hasBreakdown ? rent : monthlyCostTotal;
  const monthlySupplies = hasBreakdown ? supplies : 0;
  const monthlyUtilities = hasBreakdown ? utilities : 0;

  const wageBill = parseNum(enroll.monthlyWageBill);
  const loanRepay = parseNum(enroll.loanMonthly);
  const totalOperating =
    monthlyRent + monthlySupplies + monthlyUtilities + wageBill + loanRepay;

  const chName = (enroll.channelName && String(enroll.channelName).trim()) || "";
  const chPctRaw = enroll.channelPct === "" || enroll.channelPct == null ? 100 : parseNum(enroll.channelPct, 100);
  const channels = [{ name: chName || "Primary", percentage: chPctRaw > 0 ? chPctRaw : 100 }];

  const descLine = enroll.description ? String(enroll.description).split(/[.;\n]/)[0].trim() : "";
  const productCategory = (enroll.productCategory && enroll.productCategory.trim()) || descLine || "";

  return {
    meta: {
      business_id: enroll.businessId,
      business_name: enroll.businessName.trim(),
      date: enroll.asOfDate != null ? String(enroll.asOfDate) : "",
      type: naicsLabel,
      use_case: null,
    },
    business_profile: {
      business_type: naicsLabel,
      location: {
        city: enroll.city.trim(),
        state: enroll.state.trim(),
      },
      established: enroll.established ? String(enroll.established) : "",
      business_structure: enroll.businessStructure ? String(enroll.businessStructure).trim() : "",
    },
    revenue: {
      total_annual: monthlyRev * 12,
      channels,
    },
    costs: {
      monthly_rent: monthlyRent,
      monthly_supplies: monthlySupplies,
      monthly_utilities: monthlyUtilities,
      loan: {
        original_amount: parseNum(enroll.loanOriginal),
        remaining_balance: parseNum(enroll.loanRemaining),
        monthly_repayment: parseNum(enroll.loanMonthly),
      },
    },
    staffing: {
      total_employees: parseNum(enroll.headcount),
      monthly_wage_bill: wageBill,
    },
    products: [
      {
        category: productCategory,
        price_range: {
          min: parseNum(enroll.priceMin),
          max: parseNum(enroll.priceMax),
        },
      },
    ],
    cash: {
      current_balance: parseNum(enroll.cashBalance),
    },
    computed: {
      cogs_percentage: 0,
      gross_profit: 0,
      net_income: 0,
      break_even_monthly: 0,
      total_operating_expenses: totalOperating,
      prime_cost_ratio: 0,
    },
  };
}

/* ─── Main component ────────────────────────────────────────────── */
export default function TwinTrack() {
  const [screen, setScreen] = useState("hub");
  const [simStep, setSimStep] = useState(1);
  const [submittedPayload, setSubmittedPayload] = useState(null);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [errors, setErrors] = useState({});
  const [simApiLoading, setSimApiLoading] = useState(false);
  const [simApiError, setSimApiError] = useState(null);
  const [updateSaving, setUpdateSaving] = useState(false);
  const [updateError, setUpdateError] = useState(null);
  const [enrollSaving, setEnrollSaving] = useState(false);
  const [enrollInputSaveError, setEnrollInputSaveError] = useState(null);
  const [enrollInputSaved, setEnrollInputSaved] = useState(false);
  const [enrollSavedFilePath, setEnrollSavedFilePath] = useState(null);
  const [enrollments, setEnrollments] = useState([]);
  const [enrollmentsLoading, setEnrollmentsLoading] = useState(false);
  const [enrollmentsError, setEnrollmentsError] = useState(null);
  const [enrollmentsUnavailable, setEnrollmentsUnavailable] = useState(false);
  const [lastSimResult, setLastSimResult] = useState(() => {
    try { const r = sessionStorage.getItem("strategix_last_sim"); return r ? JSON.parse(r) : null; } catch { return null; }
  });

  const [enroll, setEnroll] = useState(() => createNewEnrollState());

  const [update, setUpdate] = useState({
    businessId: "", effectiveDate: new Date().toISOString().slice(0, 10),
    changeNotes: "", revenueCurrent: "", costsCurrent: "",
  });

  const [sim, setSim] = useState({
    businessId: "", experimentLabel: "", useCase: "pricing",
    nlDescription: "", franchiseFee: "", royaltyPct: "",
    newLocations: "", timelineMonths: "", priceChangePct: "",
    priceScope: "all", priceCategory: "", audienceShift: "",
    marketingBudgetPct: "", channelFocus: "",
  });

  useEffect(() => {
    if (screen !== "simulate" || simStep !== 1) return;
    const stored = sessionStorage.getItem(BUSINESS_ID_STORAGE_KEY);
    if (stored && !String(sim.businessId || "").trim()) {
      setSim((s) => ({ ...s, businessId: stored }));
    }
  }, [screen, simStep, sim.businessId]);

  useEffect(() => {
    const onSimStep1 = screen === "simulate" && simStep === 1;
    const onUpdate   = screen === "update";
    if (!onSimStep1 && !onUpdate) return;
    let active = true;

    const loadEnrollments = async () => {
      setEnrollmentsLoading(true);
      setEnrollmentsError(null);
      setEnrollmentsUnavailable(false);
      try {
        const res = await fetch(apiUrl("/api/enrollments"));
        const text = await res.text();
        const data = (() => {
          try { return text ? JSON.parse(text) : {}; } catch { return {}; }
        })();
        if (!res.ok) {
          throw new Error(typeof data.error === "string" ? data.error : text || `HTTP ${res.status}`);
        }
        const items = Array.isArray(data.items) ? data.items : [];
        if (!active) return;
        setEnrollments(items);

        // Auto-select first business only on the simulate screen
        if (onSimStep1 && !String(sim.businessId || "").trim() && items.length > 0) {
          const firstId = String(items[0].business_id || "").trim();
          if (firstId) {
            setSim((s) => ({ ...s, businessId: firstId }));
          }
        }
      } catch (e) {
        if (!active) return;
        setEnrollments([]);
        setEnrollmentsError(e.message || String(e));
        setEnrollmentsUnavailable(true);
      } finally {
        if (active) setEnrollmentsLoading(false);
      }
    };

    loadEnrollments();
    return () => { active = false; };
  }, [screen, simStep]);

  const validate = (fields, values) => {
    const errs = {};
    fields.forEach((f) => {
      if (!values[f] || !String(values[f]).trim()) errs[f] = "Required";
    });
    return errs;
  };

  const buildUpdatePayload = () => ({
    kind: "update_ip1",
    business_id: update.businessId,
    effective_date: update.effectiveDate,
    delta_notes: update.changeNotes,
    optional_metrics: {
      revenue_current: update.revenueCurrent ? Number(update.revenueCurrent) : null,
      costs_current: update.costsCurrent ? Number(update.costsCurrent) : null,
    },
  });

  const buildSimPayload = () => {
    const base = { business_id: sim.businessId, experiment_label: sim.experimentLabel || null, use_case: sim.useCase };
    let ip2 = {};
    if (sim.useCase === "franchising") ip2 = { franchise_fee: sim.franchiseFee ? Number(sim.franchiseFee) : null, royalty_pct: sim.royaltyPct ? Number(sim.royaltyPct) : null, planned_new_locations: sim.newLocations ? Number(sim.newLocations) : null, timeline_months: sim.timelineMonths ? Number(sim.timelineMonths) : null };
    else if (sim.useCase === "pricing") ip2 = { avg_price_change_pct: sim.priceChangePct ? Number(sim.priceChangePct) : null, scope: sim.priceScope, category_name: sim.priceScope === "category" ? sim.priceCategory : null };
    else ip2 = { target_audience_shift: sim.audienceShift, marketing_budget_change_pct: sim.marketingBudgetPct ? Number(sim.marketingBudgetPct) : null, channel_focus: sim.channelFocus };
    return { kind: "simulation_experiment", ...base, ip2, natural_language_supplement: sim.nlDescription.trim() || null };
  };

  const goHub = () => {
    setScreen("hub");
    setSubmittedPayload(null);
    setSimStep(1);
    setErrors({});
    setJsonOpen(false);
    setCopied(false);
    setSimApiError(null);
    setSimApiLoading(false);
    setUpdateError(null);
    setUpdateSaving(false);
    setEnrollSaving(false);
    setEnrollInputSaveError(null);
    setEnrollInputSaved(false);
    setEnrollSavedFilePath(null);
  };

  const runSimulationEngine = async () => {
    setSimApiError(null);
    setSimApiLoading(true);
    const bid = String(sim.businessId || "").trim() || sessionStorage.getItem(BUSINESS_ID_STORAGE_KEY) || "";
    let twin_layer = null;
    try {
      const raw = sessionStorage.getItem(TWIN_LAYER_STORAGE_KEY);
      if (raw) twin_layer = JSON.parse(raw);
    } catch {
      twin_layer = null;
    }
    if (bid && twin_layer?.meta?.business_id && twin_layer.meta.business_id !== bid) {
      twin_layer = null;
    }
    try {
      const res = await fetch(apiUrl("/api/simulate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business_id: bid || null,
          twin_layer,
          sim,
        }),
      });
      const text = await res.text();
      const data = (() => {
        try { return text ? JSON.parse(text) : {}; } catch { return {}; }
      })();
      if (!res.ok) {
        throw new Error(
          typeof data.error === "string"
            ? data.error
            : text || `HTTP ${res.status}`,
        );
      }
      setEnrollInputSaved(false);
      const simPayload = { kind: "simulation_engine_result", saved_to: data.saved_to, ...(data.result || {}) };
      setSubmittedPayload(simPayload);
      setLastSimResult(simPayload);
      try { sessionStorage.setItem("strategix_last_sim", JSON.stringify(simPayload)); } catch {}
      setScreen("submitted");
    } catch (e) {
      setSimApiError(e.message || String(e));
    } finally {
      setSimApiLoading(false);
    }
  };

  const copyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(submittedPayload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const successMeta = () => {
    if (!submittedPayload) return {};
    if (submittedPayload.kind === "simulation_engine_result") {
      return {
        label: "Simulation engine finished",
        detail: submittedPayload.saved_to
          ? `Output written to ${submittedPayload.saved_to}`
          : "OP1 / OP2 results below",
      };
    }
    if (submittedPayload.meta && submittedPayload.business_profile) {
      const idPart = submittedPayload.meta.business_id ? ` · ${submittedPayload.meta.business_id}` : "";
      return {
        label: "Business profile captured",
        detail: `${submittedPayload.meta.business_name}${idPart} · ${submittedPayload.business_profile.location.city}, ${submittedPayload.business_profile.location.state}`,
      };
    }
    if (submittedPayload.kind === "update_saved") return { label: `Business updated (v${submittedPayload.version})`, detail: `Saved to ${submittedPayload.saved_to}` };
    return { label: "Simulation queued", detail: `${submittedPayload.use_case} · ${submittedPayload.business_id}` };
  };

  const NAV_ITEMS = [
    { id: "hub", label: "Overview" },
    { id: "enroll", label: "Register business" },
    { id: "update", label: "Update info" },
    { id: "simulate", label: "Run simulation" },
    { id: "latest_dashboard", label: "Latest Simulation" },
  ];

  const SCREEN_META = {
    hub: { title: "", sub: "" },
    enroll: { title: "Register your business", sub: "" },
    update: { title: "Update business info", sub: "" },
    simulate: { title: "Run a simulation", sub: "" },
    submitted: { title: "Submitted", sub: "" },
  };

  const dashPayload = submittedPayload?.kind === "simulation_engine_result" ? submittedPayload : lastSimResult;
  if (screen === "live_dashboard" && dashPayload?.kind === "simulation_engine_result") {
    let bizData = { name: "Business", type: "", location: "" };
    const submittedBusinessName = String(dashPayload.business_name || "").trim();
    const submittedBusinessId = String(dashPayload.business_id || "").trim();
    const selectedEnrollment = enrollments.find(
      (item) => String(item.business_id || "").trim() === submittedBusinessId,
    );
    try {
      const raw = sessionStorage.getItem(TWIN_LAYER_STORAGE_KEY);
      if (raw) {
        const tw = JSON.parse(raw);
        const meta = tw.meta || {};
        const bp = tw.business_profile || {};
        const loc = bp.location || {};
        bizData = {
          name: meta.business_name || "Business",
          type: bp.business_type || "",
          location: [loc.city, loc.state].filter(Boolean).join(", "),
        };
      }
    } catch {}
    bizData = {
      ...bizData,
      name: submittedBusinessName || String(selectedEnrollment?.business_name || "").trim() || bizData.name,
    };
    return (
      <Dashboard
        biz={bizData}
        expMeta={{
          label: sim.experimentLabel || dashPayload.use_case || "Simulation",
          useCase: dashPayload.use_case || "",
          date: new Date().toLocaleDateString(),
        }}
        op1={dashPayload.op1}
        op2={dashPayload.op2}
        recommendation={dashPayload.recommendation || null}
        onBack={goHub}
      />
    );
  }

  return (
    <div style={css.root}>
      {/* ── Sidebar ── */}
      <aside style={css.sidebar}>
        <div style={css.sidebarBrand}>
          <p style={css.sidebarTag}>Strategix</p>
          <h1 style={css.sidebarTitle}>Strategix</h1>
          <p style={css.sidebarDesc}>Digital twin economic simulator. Model decisions. Compare outcomes.</p>
        </div>

        <nav style={css.navSection}>
          <p style={css.navLabel}>Actions</p>
          {NAV_ITEMS.map((n) => {
            const active = screen === n.id
              || (screen === "submitted" && n.id === "hub")
              || (screen === "live_dashboard" && n.id === "latest_dashboard");
            const isDashboardNav = n.id === "latest_dashboard";
            const dashboardAvailable = lastSimResult?.kind === "simulation_engine_result";
            return (
              <button
                key={n.id}
                type="button"
                style={{ ...css.navBtn(active), opacity: isDashboardNav && !dashboardAvailable ? 0.45 : 1 }}
                onClick={() => {
                  if (isDashboardNav) {
                    if (dashboardAvailable) setScreen("live_dashboard");
                    return;
                  }
                  setErrors({});
                  if (n.id === "simulate") setSimStep(1);
                  if (n.id === "enroll") setEnroll(createNewEnrollState());
                  setScreen(n.id);
                }}
              >
                <span style={css.navDot(active)} />
                {n.label}
              </button>
            );
          })}
        </nav>

        <div style={{ marginTop: "auto", padding: "20px 24px 0" }} />
      </aside>

      {/* ── Main ── */}
      <main style={css.main}>
        <Topbar title={SCREEN_META[screen]?.title} sub={SCREEN_META[screen]?.sub} />

        <div style={css.content}>

          {/* ── Hub ── */}
          {screen === "hub" && (
            <>
              {/* Hero */}
              <div style={{ position: "relative", padding: "20px 0 18px", marginBottom: 12, textAlign: "center" }}>
                <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: ACCENT_SOFT, margin: "0 0 10px", position: "relative" }}>
                  Strategix
                </h2>
                <p style={{ fontSize: 13, color: "#6080a0", margin: "0 auto 22px", lineHeight: 1.7, maxWidth: 500, position: "relative" }}>
                  Run your simulation before you risk it.
                </p>
              </div>

              {/* Action list */}
              <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 420, overflowY: "auto", paddingRight: 2 }}>
                {[
                  { id: "enroll",   title: "Register business", sub: "Initialize your digital twin with base financial data", icon: "+" },
                  { id: "update",   title: "Update info",        sub: "Log operational changes with effective-date versioning", icon: "↻" },
                  { id: "simulate", title: "Run simulation",     sub: "Model a decision and compare projected outcomes", icon: "▷" },
                ].map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      setErrors({});
                      if (c.id === "simulate") setSimStep(1);
                      if (c.id === "enroll") setEnroll(createNewEnrollState());
                      setScreen(c.id);
                    }}
                    style={{ display: "flex", alignItems: "center", gap: 18, width: "100%", padding: "18px 22px", borderRadius: 12, border: "none", background: "rgba(8,15,32,0.78)", cursor: "pointer", textAlign: "left", fontFamily: "inherit", transition: "background 0.2s" }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(13,148,136,0.08)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(8,15,32,0.78)"; }}
                  >
                    <div style={{ width: 42, height: 42, borderRadius: 11, background: "rgba(13,148,136,0.15)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: ACCENT, flexShrink: 0 }}>
                      {c.icon}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ margin: "0 0 3px", fontSize: 14.5, fontWeight: 600, color: "#b8d0f0" }}>{c.title}</p>
                      <p style={{ margin: 0, fontSize: 12.5, color: "#5070a0", lineHeight: 1.5 }}>{c.sub}</p>
                    </div>
                    <span style={{ fontSize: 18, color: "#2d4a70", flexShrink: 0 }}>→</span>
                  </button>
                ))}
              </div>

            </>
          )}

          {/* ── Enroll ── */}
          {screen === "enroll" && (
            <div style={css.card}>
              <Field label="Business name" error={errors.businessName}>
                <input
                  style={{ ...css.input, ...(errors.businessName ? { borderColor: "#f87171" } : {}) }}
                  value={enroll.businessName}
                  onChange={(e) => setEnroll({ ...enroll, businessName: e.target.value })}
                  onBlur={() => !enroll.businessName.trim() && setErrors((p) => ({ ...p, businessName: "Required" }))}
                  onFocus={() => setErrors((p) => ({ ...p, businessName: "" }))}
                  placeholder="e.g. Riverside Oven Co."
                />
              </Field>

              <Field label="Business ID (server-assigned)">
                <input style={{ ...css.input, opacity: 0.85 }} value={enroll.businessId || "Assigned on save"} readOnly title="Assigned by server as integer sequence (1, 2, 3...)." />
              </Field>

              <Field label="Industry (NAICS)">
                <select style={css.select} value={enroll.naics} onChange={(e) => setEnroll({ ...enroll, naics: e.target.value })}>
                  {NAICS_OPTIONS.map((o) => <option key={o.value} value={o.value} style={{ background: "#080f20" }}>{o.label}</option>)}
                </select>
              </Field>

              <div style={css.grid2}>
                <Field label="City" error={errors.city}>
                  <input style={{ ...css.input, ...(errors.city ? { borderColor: "#f87171" } : {}) }} value={enroll.city} onChange={(e) => setEnroll({ ...enroll, city: e.target.value })} onBlur={() => !enroll.city.trim() && setErrors((p) => ({ ...p, city: "Required" }))} onFocus={() => setErrors((p) => ({ ...p, city: "" }))} placeholder="Dallas" />
                </Field>
                <Field label="State" error={errors.state}>
                  <input style={{ ...css.input, ...(errors.state ? { borderColor: "#f87171" } : {}) }} value={enroll.state} onChange={(e) => setEnroll({ ...enroll, state: e.target.value })} onBlur={() => !enroll.state.trim() && setErrors((p) => ({ ...p, state: "Required" }))} onFocus={() => setErrors((p) => ({ ...p, state: "" }))} placeholder="TX" maxLength={2} />
                </Field>
              </div>

              <Field label="Established date (optional)">
                <input type="date" style={css.input} value={enroll.established} onChange={(e) => setEnroll({ ...enroll, established: e.target.value })} />
              </Field>

              <Field label="As-of date (meta.date)">
                <input type="date" style={css.input} value={enroll.asOfDate} onChange={(e) => setEnroll({ ...enroll, asOfDate: e.target.value })} />
              </Field>

              <Field label="Business structure (optional)">
                <input style={css.input} value={enroll.businessStructure} onChange={(e) => setEnroll({ ...enroll, businessStructure: e.target.value })} placeholder="LLC, sole proprietorship, partnership…" />
              </Field>

              <div style={css.sectionDivider} />
              <p style={{ fontSize: 12, color: "#4a6888", margin: "0 0 14px" }}>Financial expectations</p>

              <div style={css.grid2}>
                <Field label="Monthly revenue ($)">
                  <input style={css.input} type="number" min={0} value={enroll.monthlyRevenue} onChange={(e) => setEnroll({ ...enroll, monthlyRevenue: e.target.value })} placeholder="12000" />
                </Field>
                <Field label="Monthly costs ($)">
                  <input style={css.input} type="number" min={0} value={enroll.monthlyCosts} onChange={(e) => setEnroll({ ...enroll, monthlyCosts: e.target.value })} placeholder="8000" />
                </Field>
              </div>

              <Field label="Headcount">
                <input style={css.input} type="number" min={0} value={enroll.headcount} onChange={(e) => setEnroll({ ...enroll, headcount: e.target.value })} placeholder="4" />
              </Field>

              <Field label="Monthly wage bill ($) (optional)">
                <input style={css.input} type="number" min={0} value={enroll.monthlyWageBill} onChange={(e) => setEnroll({ ...enroll, monthlyWageBill: e.target.value })} placeholder="Leave blank if unknown" />
              </Field>

              <p style={{ fontSize: 12, color: "#4a6888", margin: "16px 0 10px" }}>Cost breakdown (optional — if set, overrides single “Monthly costs” for rent/supplies/utilities)</p>
              <div style={css.grid2}>
                <Field label="Monthly rent ($)">
                  <input style={css.input} type="number" min={0} value={enroll.monthlyRent} onChange={(e) => setEnroll({ ...enroll, monthlyRent: e.target.value })} />
                </Field>
                <Field label="Monthly supplies ($)">
                  <input style={css.input} type="number" min={0} value={enroll.monthlySupplies} onChange={(e) => setEnroll({ ...enroll, monthlySupplies: e.target.value })} />
                </Field>
                <Field label="Monthly utilities ($)">
                  <input style={css.input} type="number" min={0} value={enroll.monthlyUtilities} onChange={(e) => setEnroll({ ...enroll, monthlyUtilities: e.target.value })} />
                </Field>
                <Field label="Cash on hand ($) (optional)">
                  <input style={css.input} type="number" value={enroll.cashBalance} onChange={(e) => setEnroll({ ...enroll, cashBalance: e.target.value })} />
                </Field>
              </div>

              <p style={{ fontSize: 12, color: "#4a6888", margin: "16px 0 10px" }}>Loan (optional)</p>
              <div style={css.grid2}>
                <Field label="Original amount ($)">
                  <input style={css.input} type="number" min={0} value={enroll.loanOriginal} onChange={(e) => setEnroll({ ...enroll, loanOriginal: e.target.value })} />
                </Field>
                <Field label="Remaining balance ($)">
                  <input style={css.input} type="number" min={0} value={enroll.loanRemaining} onChange={(e) => setEnroll({ ...enroll, loanRemaining: e.target.value })} />
                </Field>
                <Field label="Monthly repayment ($)">
                  <input style={css.input} type="number" min={0} value={enroll.loanMonthly} onChange={(e) => setEnroll({ ...enroll, loanMonthly: e.target.value })} />
                </Field>
              </div>

              <p style={{ fontSize: 12, color: "#4a6888", margin: "16px 0 10px" }}>Revenue channel (optional)</p>
              <div style={css.grid2}>
                <Field label="Channel name">
                  <input style={css.input} value={enroll.channelName} onChange={(e) => setEnroll({ ...enroll, channelName: e.target.value })} placeholder="e.g. Dine-in, Retail" />
                </Field>
                <Field label="Share of revenue (%)">
                  <input style={css.input} type="number" min={0} max={100} value={enroll.channelPct} onChange={(e) => setEnroll({ ...enroll, channelPct: e.target.value })} placeholder="100" />
                </Field>
              </div>

              <Field label="What you sell / service focus">
                <textarea style={css.textarea} value={enroll.description} onChange={(e) => setEnroll({ ...enroll, description: e.target.value })} placeholder="Artisan breads, weekday lunch rush, wholesale to cafés…" />
              </Field>

              <div style={css.grid2}>
                <Field label="Primary product category (optional)">
                  <input style={css.input} value={enroll.productCategory} onChange={(e) => setEnroll({ ...enroll, productCategory: e.target.value })} placeholder="Overrides first line of description if set" />
                </Field>
                <Field label="Price range — min ($)">
                  <input style={css.input} type="number" min={0} value={enroll.priceMin} onChange={(e) => setEnroll({ ...enroll, priceMin: e.target.value })} />
                </Field>
                <Field label="Price range — max ($)">
                  <input style={css.input} type="number" min={0} value={enroll.priceMax} onChange={(e) => setEnroll({ ...enroll, priceMax: e.target.value })} />
                </Field>
              </div>

              {enrollInputSaveError && (
                <p style={{ ...css.errorText, margin: "0 0 16px" }}>{enrollInputSaveError}</p>
              )}
              <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                <button type="button" style={css.btnGhost} onClick={goHub}>← Back</button>
                <button
                  type="button"
                  style={css.btnPrimary}
                  disabled={enrollSaving}
                  onClick={async () => {
                    const errs = validate(["businessName", "city", "state"], enroll);
                    if (Object.keys(errs).length) { setErrors(errs); return; }
                    const layer = buildTwinLayerPayload(enroll);
                    let submittedTwin = layer;
                    setEnrollInputSaveError(null);
                    setEnrollInputSaved(false);
                    setEnrollSaving(true);
                    try {
                      const res = await fetch(apiUrl("/api/save-twin-layer"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ twin_layer: layer }),
                      });
                      const text = await res.text();
                      const data = (() => {
                        try { return text ? JSON.parse(text) : {}; } catch { return {}; }
                      })();
                      if (!res.ok) {
                        throw new Error(
                          typeof data.error === "string"
                            ? data.error
                            : text || `HTTP ${res.status}`,
                        );
                      }
                      const assignedId = String(data?.result?.twin_layer?.meta?.business_id || "").trim();
                      const savedTwin = data?.result?.twin_layer;
                      if (savedTwin && typeof savedTwin === "object") {
                        submittedTwin = savedTwin;
                      }
                      if (assignedId) {
                        setEnroll((prev) => ({ ...prev, businessId: assignedId }));
                        try {
                          sessionStorage.setItem(BUSINESS_ID_STORAGE_KEY, assignedId);
                          sessionStorage.setItem(TWIN_LAYER_STORAGE_KEY, JSON.stringify(submittedTwin));
                        } catch {
                          /* ignore quota / private mode */
                        }
                      }
                      setEnrollInputSaved(true);
                      setEnrollSavedFilePath(typeof data.saved_to === "string" ? data.saved_to : null);
                    } catch (e) {
                      setEnrollSavedFilePath(null);
                      setEnrollInputSaveError(
                        `Could not write enrollment file: ${e.message || String(e)}. Start the API with npm run sim-server.`,
                      );
                    } finally {
                      setEnrollSaving(false);
                    }
                    setSubmittedPayload(submittedTwin);
                    setScreen("submitted");
                  }}
                >
                  {enrollSaving ? "Saving…" : "Submit enrollment"}
                </button>
              </div>
            </div>
          )}

          {/* ── Update ── */}
          {screen === "update" && (
            <div style={css.card}>
              <Field label="Business ID" error={errors.businessId}>
                {enrollmentsUnavailable ? (
                  <input style={{ ...css.input, ...(errors.businessId ? { borderColor: "#f87171" } : {}) }} value={update.businessId} onChange={(e) => setUpdate({ ...update, businessId: e.target.value })} onBlur={() => !update.businessId.trim() && setErrors((p) => ({ ...p, businessId: "Required" }))} onFocus={() => setErrors((p) => ({ ...p, businessId: "" }))} placeholder="UUID or slug from enrollment" />
                ) : (
                  <select
                    style={{ ...css.select, ...(errors.businessId ? { borderColor: "#f87171" } : {}) }}
                    value={update.businessId}
                    onChange={(e) => { setUpdate({ ...update, businessId: e.target.value }); setErrors((p) => ({ ...p, businessId: "" })); }}
                    onBlur={() => !update.businessId.trim() && setErrors((p) => ({ ...p, businessId: "Required" }))}
                    disabled={enrollmentsLoading}
                  >
                    <option value="" style={{ background: "#080f20" }}>
                      {enrollmentsLoading ? "Loading enrollments…" : "Select a business…"}
                    </option>
                    {enrollments.map((item) => {
                      const id   = String(item.business_id   || "");
                      const name = String(item.business_name || "Unnamed business");
                      const d    = String(item.date          || "");
                      return (
                        <option key={`${id}-${item.file || d}`} value={id} style={{ background: "#080f20" }}>
                          {name} ({id}){d ? ` · ${d}` : ""}
                        </option>
                      );
                    })}
                  </select>
                )}
              </Field>
              <Field label="Effective date">
                <input type="date" style={css.input} value={update.effectiveDate} onChange={(e) => setUpdate({ ...update, effectiveDate: e.target.value })} />
              </Field>
              <Field label="What changed" error={errors.changeNotes}>
                <textarea style={{ ...css.textarea, ...(errors.changeNotes ? { borderColor: "#f87171" } : {}) }} value={update.changeNotes} onChange={(e) => setUpdate({ ...update, changeNotes: e.target.value })} onBlur={() => !update.changeNotes.trim() && setErrors((p) => ({ ...p, changeNotes: "Required" }))} onFocus={() => setErrors((p) => ({ ...p, changeNotes: "" }))} placeholder="Hired second baker; extended hours; rent renegotiated…" />
              </Field>
              <div style={css.grid2}>
                <Field label="Current revenue (optional)">
                  <input style={css.input} type="number" value={update.revenueCurrent} onChange={(e) => setUpdate({ ...update, revenueCurrent: e.target.value })} />
                </Field>
                <Field label="Current costs (optional)">
                  <input style={css.input} type="number" value={update.costsCurrent} onChange={(e) => setUpdate({ ...update, costsCurrent: e.target.value })} />
                </Field>
              </div>
              {updateError && <p style={{ ...css.errorText, marginBottom: 8 }}>{updateError}</p>}
              <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                <button type="button" style={css.btnGhost} onClick={goHub}>← Back</button>
                <button
                  type="button"
                  style={css.btnPrimary}
                  disabled={updateSaving}
                  onClick={async () => {
                    const errs = validate(["businessId", "changeNotes"], update);
                    if (Object.keys(errs).length) { setErrors(errs); return; }
                    setUpdateError(null);
                    setUpdateSaving(true);
                    try {
                      const res = await fetch(apiUrl("/api/update-twin-layer"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(buildUpdatePayload()),
                      });
                      const text = await res.text();
                      const data = (() => { try { return text ? JSON.parse(text) : {}; } catch { return {}; } })();
                      if (!res.ok) throw new Error(typeof data.error === "string" ? data.error : text || `HTTP ${res.status}`);
                      setSubmittedPayload({ kind: "update_saved", version: data.version, saved_to: data.saved_to, ...data.result });
                      setScreen("submitted");
                    } catch (e) {
                      setUpdateError(e.message || String(e));
                    } finally {
                      setUpdateSaving(false);
                    }
                  }}
                >
                  {updateSaving ? "Saving…" : "Save update"}
                </button>
              </div>
            </div>
          )}

          {/* ── Simulate ── */}
          {screen === "simulate" && (
            <div style={css.card}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <StepDots current={simStep} total={3} />
              </div>

              {simStep === 1 && (
                <>
                  {!enrollmentsUnavailable && (
                    <Field label="Select existing enrolled business">
                      <select
                        style={css.select}
                        value={sim.businessId}
                        onChange={(e) => setSim({ ...sim, businessId: e.target.value })}
                        disabled={enrollmentsLoading || enrollments.length === 0}
                      >
                        {enrollments.length === 0 && (
                          <option value="" style={{ background: "#080f20" }}>
                            {enrollmentsLoading ? "Loading enrollments..." : "No enrollments found"}
                          </option>
                        )}
                        {enrollments.map((item) => {
                          const id = String(item.business_id || "");
                          const name = String(item.business_name || "Unnamed business");
                          const d = String(item.date || "");
                          return (
                            <option key={`${id}-${item.file || d}`} value={id} style={{ background: "#080f20" }}>
                              {name} ({id}){d ? ` - ${d}` : ""}
                            </option>
                          );
                        })}
                      </select>
                    </Field>
                  )}
                  {enrollmentsUnavailable && (
                    <p style={{ fontSize: 12, color: "#4a6888", margin: "0 0 12px", lineHeight: 1.6 }}>
                      Enrollment list is unavailable right now; enter Business ID manually.
                    </p>
                  )}

                  <Field label="Business ID" error={errors.businessId}>
                    <input style={{ ...css.input, ...(errors.businessId ? { borderColor: "#f87171" } : {}) }} value={sim.businessId} onChange={(e) => setSim({ ...sim, businessId: e.target.value })} onBlur={() => !sim.businessId.trim() && setErrors((p) => ({ ...p, businessId: "Required" }))} onFocus={() => setErrors((p) => ({ ...p, businessId: "" }))} placeholder="Autofilled after enrollment; loads twin from disk" />
                  </Field>
                  {enrollmentsError && (
                    <p style={{ fontSize: 11.5, color: "#4a6888", margin: "-8px 0 12px", lineHeight: 1.5 }}>{enrollmentsError}</p>
                  )}
                  <Field label="Experiment label (optional)">
                    <input style={css.input} value={sim.experimentLabel} onChange={(e) => setSim({ ...sim, experimentLabel: e.target.value })} placeholder="Q3 price +10% test" />
                  </Field>

                  <div style={css.sectionDivider} />
                  <p style={{ ...css.fieldLabel, marginBottom: 12 }}>Simulation type</p>

                  {USE_CASES.map((u) => (
                    <label key={u.id} style={css.radioCard(sim.useCase === u.id)}>
                      <input type="radio" name="uc" checked={sim.useCase === u.id} onChange={() => setSim({ ...sim, useCase: u.id })} style={{ display: "none" }} />
                      <div style={{ color: sim.useCase === u.id ? ACCENT_SOFT : "#4a6888", marginTop: 1, flexShrink: 0 }}>
                        {u.icon}
                      </div>
                      <div>
                        <p style={{ margin: "0 0 3px", fontSize: 14, fontWeight: 600, color: sim.useCase === u.id ? "#ccfbf1" : "#6080a8" }}>{u.title}</p>
                        <p style={{ margin: 0, fontSize: 12.5, color: "#4a6888" }}>{u.blurb}</p>
                      </div>
                      <div style={{ marginLeft: "auto", width: 16, height: 16, borderRadius: "50%", border: sim.useCase === u.id ? `5px solid ${ACCENT}` : "1.5px solid rgba(255,255,255,0.15)", flexShrink: 0, marginTop: 2 }} />
                    </label>
                  ))}
                </>
              )}

              {simStep === 2 && sim.useCase === "franchising" && (
                <>
                  <div style={css.grid2}>
                    <Field label="Franchise fee ($)"><input style={css.input} type="number" value={sim.franchiseFee} onChange={(e) => setSim({ ...sim, franchiseFee: e.target.value })} /></Field>
                    <Field label="Royalty (% of revenue)"><input style={css.input} type="number" step="0.1" value={sim.royaltyPct} onChange={(e) => setSim({ ...sim, royaltyPct: e.target.value })} /></Field>
                    <Field label="New locations"><input style={css.input} type="number" min={0} value={sim.newLocations} onChange={(e) => setSim({ ...sim, newLocations: e.target.value })} /></Field>
                    <Field label="Timeline (months)"><input style={css.input} type="number" min={1} value={sim.timelineMonths} onChange={(e) => setSim({ ...sim, timelineMonths: e.target.value })} /></Field>
                  </div>
                </>
              )}

              {simStep === 2 && sim.useCase === "pricing" && (
                <>
                  <Field label="Average price change (%)">
                    <input style={css.input} type="number" step="0.5" value={sim.priceChangePct} onChange={(e) => setSim({ ...sim, priceChangePct: e.target.value })} placeholder="+8 or -3" />
                  </Field>
                  <Field label="Scope">
                    <select style={css.select} value={sim.priceScope} onChange={(e) => setSim({ ...sim, priceScope: e.target.value })}>
                      <option value="all" style={{ background: "#080f20" }}>All SKUs / menu</option>
                      <option value="category" style={{ background: "#080f20" }}>Single category</option>
                    </select>
                  </Field>
                  {sim.priceScope === "category" && (
                    <Field label="Category name">
                      <input style={css.input} value={sim.priceCategory} onChange={(e) => setSim({ ...sim, priceCategory: e.target.value })} placeholder="Pastries, beverages…" />
                    </Field>
                  )}
                </>
              )}

              {simStep === 2 && sim.useCase === "audience" && (
                <>
                  <Field label="Audience shift description">
                    <textarea style={css.textarea} value={sim.audienceShift} onChange={(e) => setSim({ ...sim, audienceShift: e.target.value })} placeholder="Move toward younger professionals; emphasize lunch grab-and-go…" />
                  </Field>
                  <div style={css.grid2}>
                    <Field label="Marketing budget change (%)">
                      <input style={css.input} type="number" step="1" value={sim.marketingBudgetPct} onChange={(e) => setSim({ ...sim, marketingBudgetPct: e.target.value })} placeholder="+25" />
                    </Field>
                    <Field label="Channel focus">
                      <input style={css.input} value={sim.channelFocus} onChange={(e) => setSim({ ...sim, channelFocus: e.target.value })} placeholder="Instagram, local events…" />
                    </Field>
                  </div>
                </>
              )}

              {simStep === 3 && (
                <>
                  <div style={{ background: "rgba(13,148,136,0.08)", border: "1px solid rgba(13,148,136,0.18)", borderRadius: 10, padding: "12px 16px", marginBottom: 18 }}>
                    <p style={{ margin: "0 0 2px", fontSize: 12.5, fontWeight: 600, color: ACCENT_SOFT }}>Optional: natural language supplement</p>
                    <p style={{ margin: 0, fontSize: 12, color: "#4a6888", lineHeight: 1.6 }}>Describe the decision in plain English. The LLM layer will map this to structured IP2 and merge it with the form values above.</p>
                  </div>
                  <div style={{ background: "rgba(13,148,136,0.06)", border: "1px solid rgba(13,148,136,0.2)", borderRadius: 10, padding: "12px 16px", marginBottom: 18 }}>
                    <p style={{ margin: "0 0 4px", fontSize: 12.5, fontWeight: 600, color: ACCENT_SOFT }}>Simulation</p>
                    <p style={{ margin: 0, fontSize: 12, color: "#4a6888", lineHeight: 1.6 }}>Use Run simulation engine to generate results for the selected use case.</p>
                  </div>
                  <Field label="Your description (optional)">
                    <textarea style={{ ...css.textarea, minHeight: 120 }} value={sim.nlDescription} onChange={(e) => setSim({ ...sim, nlDescription: e.target.value })} placeholder="e.g. I want to raise beverage prices by 10% starting in Q3 to offset rising supply costs…" />
                  </Field>
                </>
              )}

              {simStep === 3 && simApiError && (
                <p style={{ ...css.errorText, marginBottom: 12 }}>{simApiError}</p>
              )}

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20, flexWrap: "wrap", gap: 10 }}>
                <button type="button" style={css.btnGhost} onClick={() => simStep === 1 ? goHub() : setSimStep(simStep - 1)}>
                  {simStep === 1 ? "← Back" : "← Previous"}
                </button>
                {simStep < 3 ? (
                  <button
                    type="button"
                    style={css.btnPrimary}
                    onClick={() => {
                      if (simStep === 1) {
                        const errs = validate(["businessId"], sim);
                        if (Object.keys(errs).length) { setErrors(errs); return; }
                        setErrors({});
                      }
                      setSimStep(simStep + 1);
                    }}
                  >
                    Continue →
                  </button>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "flex-end" }}>
                    <button
                      type="button"
                      style={css.btnGhost}
                      disabled={simApiLoading}
                      onClick={() => { setEnrollInputSaved(false); setSubmittedPayload(buildSimPayload()); setScreen("submitted"); }}
                    >
                      Queue only (request JSON)
                    </button>
                    <button type="button" style={css.btnPrimary} disabled={simApiLoading} onClick={runSimulationEngine}>
                      {simApiLoading ? "Running…" : "Run simulation engine"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Submitted ── */}
          {screen === "submitted" && submittedPayload && (() => {
            const meta = successMeta();
            return (
              <div style={css.card}>
                <div style={css.successIcon}>
                  <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                    <path d="M5 11.5L9 15.5L17 7" stroke={ACCENT_SOFT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>

                <p style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#b0c4e8", letterSpacing: "-0.02em" }}>
                  {meta.label}
                </p>
                <p style={{ margin: "0 0 20px", fontSize: 13.5, color: "#5a7898" }}>{meta.detail}</p>

                {enrollInputSaveError && (
                  <p style={{ ...css.errorText, margin: "0 0 16px" }}>{enrollInputSaveError}</p>
                )}

                <div style={{ display: "flex", flexWrap: "wrap" }}>
                  {enrollInputSaved && enrollSavedFilePath && submittedPayload.meta && submittedPayload.business_profile && (
                    <span style={css.metaChip}>{enrollSavedFilePath}</span>
                  )}
                  {submittedPayload.kind != null && <span style={css.metaChip}>kind: {submittedPayload.kind}</span>}
                  {submittedPayload.saved_to && <span style={css.metaChip}>{submittedPayload.saved_to}</span>}
                  {submittedPayload.meta?.type && <span style={css.metaChip}>{submittedPayload.meta.type}</span>}
                  {submittedPayload.use_case && <span style={css.metaChip}>{submittedPayload.use_case}</span>}
                </div>

                <div style={css.sectionDivider} />

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: jsonOpen ? 12 : 0 }}>
                  <button
                    type="button"
                    style={{ ...css.btnGhost, fontSize: 12.5, padding: "8px 14px" }}
                    onClick={() => setJsonOpen((o) => !o)}
                  >
                    {jsonOpen ? "Hide payload ↑" : "View raw payload →"}
                  </button>
                  {jsonOpen && (
                    <button type="button" style={{ ...css.btnGhost, fontSize: 12, padding: "7px 14px" }} onClick={copyJson}>
                      {copied ? "Copied ✓" : "Copy JSON"}
                    </button>
                  )}
                </div>

                {jsonOpen && (
                  <pre style={css.pre}>{JSON.stringify(submittedPayload, null, 2)}</pre>
                )}

                <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
                  <button type="button" style={css.btnGhost} onClick={goHub}>← Return to overview</button>
                  {submittedPayload?.kind === "simulation_engine_result" ? (
                    <button type="button" style={css.btnPrimary} onClick={() => setScreen("live_dashboard")}>View Dashboard →</button>
                  ) : (
                    <button type="button" style={css.btnPrimary} onClick={() => { setSimStep(1); setScreen("simulate"); }}>Run simulation →</button>
                  )}
                </div>
              </div>
            );
          })()}

        </div>
      </main>
    </div>
  );
}
