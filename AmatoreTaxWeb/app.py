# Amatore & Co — Tax Planning Calculator v7.6.5 (States + ROI + Always-on PDF)
# Single-file Streamlit app
# ------------------------------------------------------------
# New in v7.6.5
# - State dropdown restored (with manual Effective % entry)
# - Engagement & ROI panel (Client Plan Fee, Oil & Gas, Other investment,
#   expected annual return %, projection years)
# - ROI displayed on-screen and included in PDF
# - Export & PDF buttons are ALWAYS visible (even with zero strategies)
# - Keeps robust 2025 standard deduction/lookup fixes from 7.6.4
# ------------------------------------------------------------

from __future__ import annotations

import json
import io
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import streamlit as st

# =============================
# Utilities & Core Structures
# =============================

@dataclass
class TaxInputs:
    filing_status: str = "MFJ"  # MFJ, Single, MFS, HOH
    tax_year: int = 2024        # Will be locked by tab

    # Income (ordinary bucket for now)
    wages_w2: float = 0.0
    business_income: float = 0.0  # Sch C / pass-through ordinary income
    other_income: float = 0.0     # other ordinary income (interest, ordinary div, ST gains, etc.)

    # Adjustments & Deductions
    adjustments: float = 0.0      # above-the-line
    itemized_deductions: float = 0.0
    use_standard_deduction: bool = True

    # State/Local - simple flat effective
    state_effective_rate_pct: float = 0.0

    # Retirement deferrals (employee side) — optional baseline inputs (pre-strategy)
    employee_401k_deferral: float = 0.0
    traditional_ira_contribution: float = 0.0

    # Business context for certain strategies
    reasonable_comp_w2_owner: float = 0.0


@dataclass
class BaselineResult:
    agi: float
    taxable_income: float
    federal_tax: float
    state_tax: float
    total_tax: float
    marginal_rate: float


@dataclass
class StrategyResult:
    name: str
    description: str
    change_in_taxable_income: float
    federal_tax_savings: float
    state_tax_savings: float
    total_savings: float
    notes: Optional[str] = None


# =============================
# Reference Data (States, Brackets & Standard Deduction)
# =============================

STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"
]

# 2023 & 2024 populated; 2025 values loaded.
FEDERAL_STD_DEDUCTION = {
    2023: {"Single": 13850.0, "MFJ": 27700.0, "MFS": 13850.0, "HOH": 20800.0},
    2024: {"Single": 14600.0, "MFJ": 29200.0, "MFS": 14600.0, "HOH": 21900.0},
    2025: {"Single": 15000.0, "MFJ": 30000.0, "MFS": 15000.0, "HOH": 22500.0},
}

FEDERAL_BRACKETS = {
    2023: {
        "Single": [(11000,0.10),(44725,0.12),(95375,0.22),(182100,0.24),(231250,0.32),(578125,0.35),(float("inf"),0.37)],
        "MFJ":    [(22000,0.10),(89450,0.12),(190750,0.22),(364200,0.24),(462500,0.32),(693750,0.35),(float("inf"),0.37)],
        "MFS":    [(11000,0.10),(44725,0.12),(95375,0.22),(182100,0.24),(231250,0.32),(346875,0.35),(float("inf"),0.37)],
        "HOH":    [(15700,0.10),(59850,0.12),(95350,0.22),(182100,0.24),(231250,0.32),(578100,0.35),(float("inf"),0.37)],
    },
    2024: {
        "Single": [(11600,0.10),(47150,0.12),(100525,0.22),(191950,0.24),(243725,0.32),(609350,0.35),(float("inf"),0.37)],
        "MFJ":    [(23200,0.10),(94300,0.12),(201050,0.22),(383900,0.24),(487450,0.32),(731200,0.35),(float("inf"),0.37)],
        "MFS":    [(11600,0.10),(47150,0.12),(100525,0.22),(191950,0.24),(243725,0.32),(365600,0.35),(float("inf"),0.37)],
        "HOH":    [(16550,0.10),(63100,0.12),(100500,0.22),(191950,0.24),(243700,0.32),(609350,0.35),(float("inf"),0.37)],
    },
    2025: {
        "Single": [(11925,0.10),(48475,0.12),(103350,0.22),(197300,0.24),(250525,0.32),(626350,0.35),(float("inf"),0.37)],
        "MFJ":    [(23850,0.10),(96950,0.12),(206700,0.22),(394600,0.24),(501050,0.32),(751600,0.35),(float("inf"),0.37)],
        "MFS":    [(11925,0.10),(48475,0.12),(103350,0.22),(197300,0.24),(250525,0.32),(375800,0.35),(float("inf"),0.37)],
        "HOH":    [(17000,0.10),(64850,0.12),(103350,0.22),(197300,0.24),(250500,0.32),(626350,0.35),(float("inf"),0.37)],
    },
}


def get_std_deduction(tax_year: int, filing_status: str, use_standard: bool, itemized: float) -> float:
    """Return numeric standard deduction for given year/status with robust coercion.
    Always returns a float; never a dict/list.
    """
    try:
        tax_year = int(tax_year)
    except Exception:
        tax_year = 2024

    if not use_standard:
        try:
            return float(max(0.0, itemized))
        except Exception:
            return 0.0

    sd_map = FEDERAL_STD_DEDUCTION.get(tax_year, FEDERAL_STD_DEDUCTION[2024])
    if not isinstance(sd_map, dict):
        try:
            return float(sd_map)
        except Exception:
            return 0.0

    val = sd_map.get(filing_status, sd_map.get("MFJ", 0.0))
    if isinstance(val, (list, tuple)):
        val = val[0] if val else 0.0
    elif isinstance(val, dict):
        val = val.get("value", 0.0)

    try:
        return float(val)
    except Exception:
        return 0.0


def compute_federal_tax(filing_status: str, taxable_income: float, tax_year: int) -> tuple[float, float]:
    """Returns (federal_tax, marginal_rate). Uses year-aware bracket tables with type safety."""
    try:
        tax_year = int(tax_year)
    except Exception:
        tax_year = 2024

    ti = max(0.0, float(taxable_income))
    tax = 0.0
    marginal = 0.0

    year_map = FEDERAL_BRACKETS.get(tax_year, FEDERAL_BRACKETS[2024])
    brackets = year_map.get(filing_status, year_map.get("MFJ"))

    prev_cap = 0.0
    for cap, rate in brackets:
        if ti > cap:
            tax += (cap - prev_cap) * rate
            prev_cap = cap
        else:
            tax += (ti - prev_cap) * rate
            marginal = rate
            break
    else:
        marginal = brackets[-1][1]

    return round(tax, 2), marginal


def compute_baseline(inputs: TaxInputs) -> BaselineResult:
    gross = float(inputs.wages_w2) + float(inputs.business_income) + float(inputs.other_income)
    agi = max(0.0, gross - float(inputs.adjustments))

    std_or_itemized = get_std_deduction(
        inputs.tax_year, inputs.filing_status, inputs.use_standard_deduction, inputs.itemized_deductions
    )

    predeferrals = float(inputs.employee_401k_deferral) + float(inputs.traditional_ira_contribution)

    taxable_income = max(0.0, agi - std_or_itemized - predeferrals)

    fed_tax, marginal_rate = compute_federal_tax(inputs.filing_status, taxable_income, inputs.tax_year)
    state_tax = round(taxable_income * (inputs.state_effective_rate_pct / 100.0), 2)
    total_tax = round(fed_tax + state_tax, 2)

    return BaselineResult(agi=round(agi,2), taxable_income=round(taxable_income,2), federal_tax=fed_tax,
                          state_tax=state_tax, total_tax=total_tax, marginal_rate=marginal_rate)


# =============================
# Strategy Engines
# =============================

def _state_savings(delta_taxable: float, state_effective_rate_pct: float) -> float:
    return round(max(0.0, delta_taxable) * (state_effective_rate_pct / 100.0), 2)


def strat_augusta_rule(baseline: BaselineResult, inputs: TaxInputs, fair_daily_rate: float, days: int,
                       description_override: Optional[str] = None) -> StrategyResult:
    days = max(0, min(14, int(days)))
    rent = max(0.0, float(fair_daily_rate) * days)
    fed_save = round(rent * baseline.marginal_rate, 2)
    st_save = _state_savings(rent, inputs.state_effective_rate_pct)
    desc = description_override or ("Rent home to business up to 14 days at FMV; owner excludes income; business deducts expense.")
    return StrategyResult(name="Augusta Rule", description=desc, change_in_taxable_income=-rent,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Modeled at FMV ${fair_daily_rate:,.0f} x {days} days = ${rent:,.2f}.")


def strat_section_179(baseline: BaselineResult, inputs: TaxInputs, equipment_cost: float, elected_179: float,
                      description_override: Optional[str] = None) -> StrategyResult:
    equipment_cost = max(0.0, float(equipment_cost))
    elected = max(0.0, min(float(elected_179), equipment_cost))
    fed_save = round(elected * baseline.marginal_rate, 2)
    st_save = _state_savings(elected, inputs.state_effective_rate_pct)
    desc = description_override or ("Elect to expense qualified equipment under IRC §179 (subject to limits/phaseouts).")
    return StrategyResult(name="Section 179 (Accelerated Expensing)", description=desc, change_in_taxable_income=-elected,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Elected ${elected:,.2f} on equipment cost ${equipment_cost:,.2f}.")


def strat_captive_831b(baseline: BaselineResult, inputs: TaxInputs, annual_premium: float, cap_limit: float = 2900000.0,
                       description_override: Optional[str] = None) -> StrategyResult:
    premium = max(0.0, float(annual_premium))
    deductible = min(premium, max(0.0, float(cap_limit)))
    fed_save = round(deductible * baseline.marginal_rate, 2)
    st_save = _state_savings(deductible, inputs.state_effective_rate_pct)
    desc = description_override or ("Elect under §831(b) for qualifying micro-captive; treat premiums as deductible (planning estimate).")
    return StrategyResult(name="Captive Insurance (§831(b))", description=desc, change_in_taxable_income=-deductible,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Modeled deductible premium ${deductible:,.2f} (cap ${cap_limit:,.0f}).")


def strat_employee_deferral(baseline: BaselineResult, inputs: TaxInputs, plan_type: str, contribution: float,
                            description_override: Optional[str] = None) -> StrategyResult:
    contrib = max(0.0, float(contribution))
    fed_save = round(contrib * baseline.marginal_rate, 2)
    st_save = _state_savings(contrib, inputs.state_effective_rate_pct)
    desc = description_override or (f"Pre-tax {plan_type} employee deferral (traditional)")
    return StrategyResult(name=f"{plan_type} Deferral", description=desc, change_in_taxable_income=-contrib,
                          federal_tax_savings=fed_save, state_tax_savings=st_save, total_savings=round(fed_save+st_save,2),
                          notes=f"Modeled contribution ${contrib:,.2f}.")


# =============================
# Streamlit UI (Multi‑Year Tabs)
# =============================

st.set_page_config(page_title="Amatore & Co — Tax Planning Calculator v7.6.5", page_icon="📊", layout="wide")

st.title("Amatore & Co — Tax Planning Calculator v7.6.5")
st.caption("Planning-only estimates. For educational use; not tax advice.")

with st.expander("About this version"):
    st.markdown(
        """
        **What's new (v7.6.5)**
        - State dropdown + effective % field.
        - Engagement & ROI panel (plan fee, investments, expected % and years).
        - ROI shown on-screen and in PDF; exports visible even with 0 strategies.
        - 2023/2024 tables + 2025 values loaded (updateable). Robust type safety.
        """
    )


def render_year_page(year: int, key_prefix: str = ""):
    """Render one full calculator page for a given tax year."""
    st.subheader(f"Baseline Inputs — {year}")

    st.sidebar.header(f"Client Inputs — {year}")

    # Client metadata
    client_name = st.sidebar.text_input("Client Name", value="", key=f"{key_prefix}client_name")
    client_id = st.sidebar.text_input("Client ID / File #", value="", key=f"{key_prefix}client_id")
    preparer = st.sidebar.text_input("Preparer", value="", key=f"{key_prefix}preparer")
    notes_meta = st.sidebar.text_area("Engagement Notes (short)", value="", key=f"{key_prefix}eng_notes")

    filing_status = st.sidebar.selectbox("Filing Status", ["MFJ", "Single", "MFS", "HOH"], index=0, key=f"{key_prefix}fs")

    col_fs1, col_fs2 = st.sidebar.columns(2)
    with col_fs1:
        st.number_input("Tax Year", min_value=2023, max_value=2026, value=year, step=1, key=f"{key_prefix}ty", disabled=True)
    with col_fs2:
        state_selected = st.selectbox("State", STATES, index=STATES.index("CA") if "CA" in STATES else 0, key=f"{key_prefix}state_sel")
    state_rate = st.number_input("State Effective % (enter your effective rate)", min_value=0.0, max_value=15.0, value=0.0, step=0.1, format="%.1f", key=f"{key_prefix}state")

    st.sidebar.subheader("Income — Personal & Business")
    # Personal
    wages = st.sidebar.number_input("W-2 Wages", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}w2")
    interest_inc = st.sidebar.number_input("Interest Income (1099-INT)", min_value=0.0, value=0.0, step=250.0, key=f"{key_prefix}int")
    div_ordinary = st.sidebar.number_input("Dividends (Ordinary)", min_value=0.0, value=0.0, step=250.0, key=f"{key_prefix}divo")
    div_qualified = st.sidebar.number_input("Dividends (Qualified)", min_value=0.0, value=0.0, step=250.0, key=f"{key_prefix}divq")
    stcg = st.sidebar.number_input("Capital Gains (Short-Term)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}stcg")
    ltcg = st.sidebar.number_input("Capital Gains (Long-Term)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}ltcg")

    # Business / Pass-through
    se_income = st.sidebar.number_input("Schedule C (Self-Employment) Net", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}schc")
    k1_ordinary = st.sidebar.number_input("K-1 Ordinary Business Income", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}k1")
    rental_net = st.sidebar.number_input("Rental Real Estate Net (Sch E)", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}rent")

    # Aggregate for current engine (ordinary brackets only for now; LTCG/Qualified div noted for future module)
    biz_inc = se_income + k1_ordinary + rental_net
    other_inc = interest_inc + div_ordinary + stcg + div_qualified + ltcg

    st.sidebar.subheader("Adjustments & Deductions")
    adj = st.sidebar.number_input("Above-the-line Adjustments", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}adj")
    use_std = st.sidebar.checkbox("Use Standard Deduction", value=True, key=f"{key_prefix}use_std")
    itemized = 0.0
    if not use_std:
        itemized = st.sidebar.number_input("Itemized Deductions", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}item")

    st.sidebar.subheader("Pre-Strategy Retirement (optional)")
    pre_401k = st.sidebar.number_input("Employee 401(k) Deferral (traditional)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}401k")
    pre_ira = st.sidebar.number_input("Traditional IRA Contribution", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}ira")

    # Engagement & ROI
    st.sidebar.subheader("Engagement & ROI")
    planning_fee = st.sidebar.number_input("Client Plan Fee ($)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}fee")
    oil_gas = st.sidebar.number_input("Oil & Gas Investment", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}oilgas")
    other_invest = st.sidebar.number_input("Other Investment", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}otherinv")
    exp_return_pct = st.sidebar.number_input("Expected Annual Return %", min_value=0.0, max_value=50.0, value=0.0, step=0.1, format="%.1f", key=f"{key_prefix}retpct")
    proj_years = st.sidebar.number_input("Projection Years", min_value=1, max_value=50, value=1, step=1, key=f"{key_prefix}years")

    inputs = TaxInputs(
        filing_status=filing_status,
        tax_year=year,
        wages_w2=wages,
        business_income=biz_inc,
        other_income=other_inc,
        adjustments=adj,
        itemized_deductions=itemized,
        use_standard_deduction=use_std,
        state_effective_rate_pct=state_rate,
        employee_401k_deferral=pre_401k,
        traditional_ira_contribution=pre_ira,
    )

    base = compute_baseline(inputs)

    mcols = st.columns(6)
    mcols[0].metric("AGI", f"${base.agi:,.2f}")
    mcols[1].metric("Taxable Income", f"${base.taxable_income:,.2f}")
    mcols[2].metric("Federal Tax", f"${base.federal_tax:,.2f}")
    mcols[3].metric("State Tax", f"${base.state_tax:,.2f}")
    mcols[4].metric("Total Tax", f"${base.total_tax:,.2f}")
    mcols[5].metric("Marginal Rate", f"{int(base.marginal_rate*100)}%")

    st.divider()

    st.subheader(f"Strategies — {year}")
    st.caption("Note: Current engine treats all income at ordinary rates. Preferential LTCG/Qualified Div module coming next.")

    strategy_results: List[StrategyResult] = []

    # Augusta Rule
    with st.expander("Augusta Rule (§280A(g))"):
        c1, c2, c3 = st.columns([1,1,2])
        with c1:
            aug_rate = st.number_input("Fair Market Daily Rate ($)", min_value=0.0, value=0.0, step=50.0, key=f"{key_prefix}aug_rate")
        with c2:
            aug_days = st.number_input("Days (max 14)", min_value=0, max_value=14, value=0, step=1, key=f"{key_prefix}aug_days")
        with c3:
            st.caption("Rent personal residence to your business up to 14 days/year. Income excluded; business deducts.")
        if (aug_rate > 0) and (aug_days > 0):
            strategy_results.append(strat_augusta_rule(base, inputs, aug_rate, int(aug_days)))

    # Section 179
    with st.expander("Section 179 (Accelerated Expensing)"):
        s1, s2 = st.columns(2)
        with s1:
            eq_cost = st.number_input("Qualified Equipment Cost", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}179_cost")
        with s2:
            elect_179 = st.number_input("Elect §179 Amount", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}179_elect")
        st.caption("Simplified model — ignores phaseouts/limitations. Update for full compliance as needed.")
        if elect_179 > 0:
            strategy_results.append(strat_section_179(base, inputs, eq_cost, elect_179))

    # Captive Insurance 831(b)
    with st.expander("Captive Insurance (§831(b))"):
        c1, c2 = st.columns(2)
        with c1:
            premium = st.number_input("Annual Premium (modeled deductible)", min_value=0.0, value=0.0, step=10000.0, key=f"{key_prefix}cap_prem")
        with c2:
            cap = st.number_input("§831(b) Annual Limit", min_value=500000.0, max_value=5000000.0, value=2900000.0, step=50000.0, key=f"{key_prefix}cap_limit")
        st.caption("Planning-only estimate. Eligibility/risk rules not evaluated here.")
        if premium > 0:
            strategy_results.append(strat_captive_831b(base, inputs, premium, cap))

    # Additional employee deferral
    with st.expander("Additional Employee Retirement Deferral"):
        plan = st.selectbox("Plan Type", ["401(k)", "403(b)", "457(b)", "Simple IRA"], index=0, key=f"{key_prefix}plan")
        addl_def = st.number_input("Additional Pre-tax Contribution", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}addl_def")
        if addl_def > 0:
            strategy_results.append(strat_employee_deferral(base, inputs, plan, addl_def))

    # ----------------- Reporting & ROI (ALWAYS visible) -----------------
    st.subheader("Strategy Savings Summary")

    total_fed = sum(s.federal_tax_savings for s in strategy_results)
    total_state = sum(s.state_tax_savings for s in strategy_results)
    total_all = sum(s.total_savings for s in strategy_results)

    tcols = st.columns(3)
    tcols[0].metric("Federal Savings", f"${total_fed:,.2f}")
    tcols[1].metric("State Savings", f"${total_state:,.2f}")
    tcols[2].metric("Total Savings", f"${total_all:,.2f}")

    # ROI calculations (always show)
    principal = oil_gas + other_invest
    rate = exp_return_pct / 100.0
    fv = principal * ((1 + rate) ** proj_years)
    projected_investment_gain = max(0.0, fv - principal)
    total_costs = planning_fee + principal
    total_gain = total_all + projected_investment_gain
    roi_pct = (total_gain / total_costs * 100.0) if total_costs > 0 else None

    rcols = st.columns(4)
    rcols[0].metric("Planning Fee", f"${planning_fee:,.2f}")
    rcols[1].metric("Invested (principal)", f"${principal:,.2f}")
    rcols[2].metric("Proj. Investment Gain", f"${projected_investment_gain:,.2f}")
    rcols[3].metric("ROI %", f"{roi_pct:,.2f}%" if roi_pct is not None else "—")

    st.markdown("---")

    # Strategy cards (only if any)
    if strategy_results:
        for s in strategy_results:
            with st.container(border=True):
                st.markdown(f"### {s.name}")
                st.write(s.description)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Δ Taxable Income", f"${s.change_in_taxable_income:,.2f}")
                c2.metric("Federal Savings", f"${s.federal_tax_savings:,.2f}")
                c3.metric("State Savings", f"${s.state_tax_savings:,.2f}")
                c4.metric("Total Savings", f"${s.total_savings:,.2f}")
                if s.notes:
                    st.caption(s.notes)
    else:
        st.info("No strategies added yet — ROI and exports are still available below.")

    # ----------------- Export (ALWAYS visible) -----------------
    st.markdown("### Export")
    import pandas as pd
    df = pd.DataFrame([
        {
            "Strategy": s.name,
            "Description": s.description,
            "Delta Taxable": s.change_in_taxable_income,
            "Federal Savings": s.federal_tax_savings,
            "State Savings": s.state_tax_savings,
            "Total Savings": s.total_savings,
            "Notes": s.notes or "",
        }
        for s in strategy_results
    ])

    csv_buf = io.StringIO(); df.to_csv(csv_buf, index=False)
    st.download_button("Download CSV", csv_buf.getvalue(), file_name=f"strategy_savings_{year}.csv", mime="text/csv")

    snapshot = {
        "version": "v7.6.5",
        "year": year,
        "client": {"name": client_name, "id": client_id, "preparer": preparer, "notes": notes_meta, "state": state_selected},
        "engagement": {"planning_fee": planning_fee, "oil_gas": oil_gas, "other_invest": other_invest, "expected_return_pct": exp_return_pct, "years": int(proj_years)},
        "income_breakdown": {
            "w2": wages,
            "interest": interest_inc,
            "dividends_ordinary": div_ordinary,
            "dividends_qualified": div_qualified,
            "short_term_gains": stcg,
            "long_term_gains": ltcg,
            "schedule_c": se_income,
            "k1_ordinary": k1_ordinary,
            "rental_net": rental_net,
        },
        "inputs": asdict(inputs),
        "baseline": asdict(base),
        "strategies": [asdict(s) for s in strategy_results],
        "totals": {"federal": total_fed, "state": total_state, "all": total_all, "projected_investment_gain": projected_investment_gain, "roi_percent": roi_pct},
    }
    st.download_button("Download JSON Snapshot", data=json.dumps(snapshot, indent=2),
                       file_name=f"amatore_tax_planner_{year}_snapshot.json", mime="application/json")

    # PDF summary (ALWAYS visible; guarded if ReportLab missing)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import inch
        pdf_bytes = io.BytesIO()
        c = rl_canvas.Canvas(pdf_bytes, pagesize=letter)
        width, height = letter
        y = height - 1*inch

        c.setFont('Helvetica-Bold', 14)
        c.drawString(1*inch, y, f"Amatore & Co — Tax Planning Summary ({year})")
        y -= 0.3*inch

        c.setFont('Helvetica', 10)
        c.drawString(1*inch, y, f"Client: {client_name or '—'}    File#: {client_id or '—'}    Preparer: {preparer or '—'}    State: {state_selected}")
        y -= 0.25*inch
        if notes_meta:
            c.drawString(1*inch, y, f"Notes: {notes_meta[:80]}")
            y -= 0.2*inch

        c.setFont('Helvetica-Bold', 12); c.drawString(1*inch, y, "Baseline"); y -= 0.22*inch
        c.setFont('Helvetica', 10)
        c.drawString(1*inch, y, f"AGI: ${base.agi:,.2f}   Taxable: ${base.taxable_income:,.2f}   Fed: ${base.federal_tax:,.2f}   State: ${base.state_tax:,.2f}   Total: ${base.total_tax:,.2f}")
        y -= 0.3*inch

        c.setFont('Helvetica-Bold', 12); c.drawString(1*inch, y, "Income Breakdown"); y -= 0.22*inch
        c.setFont('Helvetica', 10)
        for label, val in [("W-2 Wages", wages),("Interest", interest_inc),("Dividends (Ord)", div_ordinary),("Dividends (Qual)", div_qualified),
                           ("Cap Gains (ST)", stcg),("Cap Gains (LT)", ltcg),("Schedule C", se_income),("K-1 Ordinary", k1_ordinary),("Rental Net", rental_net)]:
            c.drawString(1*inch, y, f"{label}: ${val:,.2f}")
            y -= 0.18*inch
            if y < 1.2*inch:
                c.showPage(); y = height - 1*inch

        if strategy_results:
            c.setFont('Helvetica-Bold', 12); c.drawString(1*inch, y, "Strategies"); y -= 0.22*inch
            c.setFont('Helvetica', 10)
            for s in strategy_results:
                c.drawString(1*inch, y, f"• {s.name} — Savings: ${s.total_savings:,.2f}")
                y -= 0.18*inch
                if s.notes:
                    c.drawString(1.2*inch, y, f"{(s.notes or '')[:90]}")
                    y -= 0.18*inch
                if y < 1.2*inch:
                    c.showPage(); y = height - 1*inch

        c.setFont('Helvetica-Bold', 12)
        c.drawString(1*inch, y, f"Total Strategy Savings: ${total_all:,.2f}")
        y -= 0.22*inch

        # ROI block
        c.setFont('Helvetica-Bold', 12); c.drawString(1*inch, y, "Return on Investment (ROI)"); y -= 0.22*inch
        c.setFont('Helvetica', 10)
        c.drawString(1*inch, y, f"Planning Fee: ${planning_fee:,.2f}"); y -= 0.18*inch
        c.drawString(1*inch, y, f"Invested Principal (Oil & Gas + Other): ${principal:,.2f}"); y -= 0.18*inch
        c.drawString(1*inch, y, f"Projection: {int(proj_years)} yrs @ {exp_return_pct:.1f}% → Projected Investment Gain: ${projected_investment_gain:,.2f}"); y -= 0.18*inch
        c.drawString(1*inch, y, f"Total Costs: ${total_costs:,.2f}"); y -= 0.18*inch
        c.drawString(1*inch, y, f"ROI %: {(roi_pct or 0.0):,.2f}%")

        c.showPage(); c.save(); pdf_bytes.seek(0)
        st.download_button("Download Client PDF Summary", data=pdf_bytes,
                           file_name=f"Amatore_Tax_Summary_{year}.pdf", mime="application/pdf")
    except Exception as e:
        st.warning(f"PDF generation unavailable: {e}")


# Render multi-year tabs

tabs = st.tabs(["2023", "2024", "2025"])
with tabs[0]:
    render_year_page(2023, key_prefix="y23_")
with tabs[1]:
    render_year_page(2024, key_prefix="y24_")
with tabs[2]:
    render_year_page(2025, key_prefix="y25_")

st.markdown("---")

with st.expander("Implementation Notes & To‑Do for v7.7"):
    st.markdown(
        """
        - Add preferential LTCG/qualified-dividends rate module per year.
        - Owner-comp optimization and payroll split modeling.
        - QBI (§199A) interaction model (phase-outs, W-2/UBIA tests).
        - Cost segregation & bonus depreciation with class-life splits.
        - Login/client save + paywall (lightweight backend/auth).
        """
    )
