# Amatore & Co — Tax Planning Calculator v7.7.1
# Single-file Streamlit app
# ------------------------------------------------------------
# New in v7.7.1 (Client-Simple PDF)
# - Simplified PDF: Strategies (brief), Taxable Income Before/After, Amount Owed Before/After,
#   ROI summary, and Fee Options.
# - Fee options are editable in sidebar (Success % and Hybrid % + Fixed).
# Prior: Payments/withholding, Owner W-2 toggle, S-Corp K-1, Oil & Gas strategy (ROI uses it),
#        auto state effective %, exports/PDF always visible, 2023–2025 tabs.
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
    business_income: float = 0.0  # Sch C / pass-through ordinary
    other_income: float = 0.0     # ordinary (interest, ordinary div, ST gains, etc.)

    # Adjustments & Deductions
    adjustments: float = 0.0
    itemized_deductions: float = 0.0
    use_standard_deduction: bool = True

    # State (effective flat for planning)
    state_effective_rate_pct: float = 0.0

    # Retirement deferrals (employee side)
    employee_401k_deferral: float = 0.0
    traditional_ira_contribution: float = 0.0

    # Payments & Withholding
    fed_withholding: float = 0.0
    fed_estimated: float = 0.0
    state_withholding: float = 0.0
    state_estimated: float = 0.0

    # Business context
    reasonable_comp_w2_owner: float = 0.0


@dataclass
class BaselineResult:
    agi: float
    taxable_income: float
    federal_tax: float
    state_tax: float
    total_tax: float
    marginal_rate: float

    # Payments / Balances
    federal_payments: float
    state_payments: float
    total_payments: float
    federal_balance_due: float   # >0 owe, <0 refund
    state_balance_due: float
    combined_balance_due: float


@dataclass
class StrategyResult:
    name: str
    description: str
    change_in_taxable_income: float   # negative = decreases taxable income
    federal_tax_savings: float
    state_tax_savings: float
    total_savings: float
    notes: Optional[str] = None


# =============================
# Reference Data (States, Brackets & Standard Deduction)
# =============================

STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI",
    "MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY"
]

# Firm-configurable EFFECTIVE state rate defaults (% of taxable income).
STATE_EFFECTIVE_DEFAULTS: Dict[str, Optional[float]] = {
    "AK": 0.0, "FL": 0.0, "NV": 0.0, "NH": 0.0, "SD": 0.0, "TN": 0.0, "TX": 0.0, "WA": 0.0, "WY": 0.0,
    "AL": 3.0, "AR": 3.5, "AZ": 2.5, "CA": 6.5, "CO": 3.0, "CT": 4.5, "DC": 5.5, "DE": 4.0, "GA": 4.0,
    "HI": 4.0, "ID": 3.5, "IL": 4.5, "IN": 3.5, "IA": 4.0, "KS": 4.0, "KY": 3.5, "LA": 3.0, "ME": 4.0,
    "MD": 4.0, "MA": 4.5, "MI": 3.5, "MN": 5.0, "MS": 3.0, "MO": 3.0, "MT": 3.5, "NE": 4.0, "NJ": 5.0,
    "NM": 3.5, "NY": 6.0, "NC": 3.5, "ND": 2.5, "OH": 3.0, "OK": 3.0, "OR": 6.0, "PA": 3.1, "RI": 4.0,
    "SC": 3.5, "UT": 3.5, "VT": 4.0, "VA": 4.0, "WV": 3.5, "WI": 4.0,
}

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
    try:
        tax_year = int(tax_year)
    except Exception:
        tax_year = 2024
    ti = max(0.0, float(taxable_income))
    tax = 0.0
    marginal = 0.0
    brackets = FEDERAL_BRACKETS.get(tax_year, FEDERAL_BRACKETS[2024]).get(filing_status, FEDERAL_BRACKETS[2024]["MFJ"])
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
    std_or_itemized = get_std_deduction(inputs.tax_year, inputs.filing_status, inputs.use_standard_deduction, inputs.itemized_deductions)
    predeferrals = float(inputs.employee_401k_deferral) + float(inputs.traditional_ira_contribution)
    taxable_income = max(0.0, agi - std_or_itemized - predeferrals)
    fed_tax, marginal_rate = compute_federal_tax(inputs.filing_status, taxable_income, inputs.tax_year)
    state_tax = round(taxable_income * (inputs.state_effective_rate_pct / 100.0), 2)
    total_tax = round(fed_tax + state_tax, 2)

    fed_payments = float(inputs.fed_withholding) + float(inputs.fed_estimated)
    st_payments = float(inputs.state_withholding) + float(inputs.state_estimated)
    total_payments = fed_payments + st_payments

    federal_balance_due = round(fed_tax - fed_payments, 2)
    state_balance_due = round(state_tax - st_payments, 2)
    combined_balance_due = round((fed_tax + state_tax) - total_payments, 2)

    return BaselineResult(
        agi=round(agi,2),
        taxable_income=round(taxable_income,2),
        federal_tax=fed_tax,
        state_tax=state_tax,
        total_tax=total_tax,
        marginal_rate=marginal_rate,
        federal_payments=round(fed_payments,2),
        state_payments=round(st_payments,2),
        total_payments=round(total_payments,2),
        federal_balance_due=federal_balance_due,
        state_balance_due=state_balance_due,
        combined_balance_due=combined_balance_due,
    )

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
    desc = description_override or ("Rent your home to your business up to 14 days — excluded from income; business deducts.")
    return StrategyResult(name="Augusta Rule", description=desc, change_in_taxable_income=-rent,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"FMV ${fair_daily_rate:,.0f} × {days} days = ${rent:,.2f}.")

def strat_section_179(baseline: BaselineResult, inputs: TaxInputs, equipment_cost: float, elected_179: float,
                      description_override: Optional[str] = None) -> StrategyResult:
    equipment_cost = max(0.0, float(equipment_cost))
    elected = max(0.0, min(float(elected_179), equipment_cost))
    fed_save = round(elected * baseline.marginal_rate, 2)
    st_save = _state_savings(elected, inputs.state_effective_rate_pct)
    desc = description_override or ("Expense qualifying equipment immediately under §179 (subject to limits).")
    return StrategyResult(name="Section 179", description=desc, change_in_taxable_income=-elected,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Elected ${elected:,.2f} on cost ${equipment_cost:,.2f}.")

def strat_captive_831b(baseline: BaselineResult, inputs: TaxInputs, annual_premium: float, cap_limit: float = 2900000.0,
                       description_override: Optional[str] = None) -> StrategyResult:
    premium = max(0.0, float(annual_premium))
    deductible = min(premium, max(0.0, float(cap_limit)))
    fed_save = round(deductible * baseline.marginal_rate, 2)
    st_save = _state_savings(deductible, inputs.state_effective_rate_pct)
    desc = description_override or ("Deduct risk-appropriate premiums paid to a qualifying micro-captive (§831(b)).")
    return StrategyResult(name="Captive Insurance (§831(b))", description=desc, change_in_taxable_income=-deductible,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Modeled deductible premium ${deductible:,.2f} (cap ${cap_limit:,.0f}).")

def strat_employee_deferral(baseline: BaselineResult, inputs: TaxInputs, plan_type: str, contribution: float,
                            description_override: Optional[str] = None) -> StrategyResult:
    contrib = max(0.0, float(contribution))
    fed_save = round(contrib * baseline.marginal_rate, 2)
    st_save = _state_savings(contrib, inputs.state_effective_rate_pct)
    desc = description_override or (f"Shift wages into pre-tax {plan_type} contributions to lower current taxable income.")
    return StrategyResult(name=f"{plan_type} Deferral", description=desc, change_in_taxable_income=-contrib,
                          federal_tax_savings=fed_save, state_tax_savings=st_save, total_savings=round(fed_save+st_save,2),
                          notes=f"Contribution ${contrib:,.2f}.")

def strat_oil_gas_idc(baseline: BaselineResult, inputs: TaxInputs, investment_amount: float, idc_percent: float,
                      description_override: Optional[str] = None) -> StrategyResult:
    amt = max(0.0, float(investment_amount))
    pct = max(0.0, min(100.0, float(idc_percent))) / 100.0
    deductible = amt * pct
    fed_save = round(deductible * baseline.marginal_rate, 2)
    st_save = _state_savings(deductible, inputs.state_effective_rate_pct)
    desc = description_override or ("Deduct the intangible drilling cost (IDC) portion of Oil & Gas investment at ordinary rates.")
    return StrategyResult(name="Oil & Gas (IDC)", description=desc, change_in_taxable_income=-deductible,
                          federal_tax_savings=fed_save, state_tax_savings=st_save,
                          total_savings=round(fed_save+st_save,2),
                          notes=f"Investment ${amt:,.2f}, IDC {pct*100:.0f}% → deductible ${deductible:,.2f}.")

# =============================
# Streamlit UI (Multi-Year Tabs)
# =============================

st.set_page_config(page_title="Amatore & Co — Tax Planning Calculator v7.7.1", page_icon="📊", layout="wide")

st.title("Amatore & Co — Tax Planning Calculator v7.7.1")
st.caption("Planning-only estimates. For educational use; not tax advice.")

with st.expander("About this version"):
    st.markdown(
        """
        **What's new (v7.7.1)** — Simple PDF for clients & team:
        - Strategies (brief), Taxable Income Before/After, Amount Owed Before/After, ROI, Fee Options.
        - Keeps: state auto effective %, Oil & Gas as strategy (ROI uses it), withholdings/estimates, Owner W-2 toggle, exports.
        """
    )

def _state_rate_input(key_prefix: str, state_selected: str) -> float:
    rate_key = f"{key_prefix}state_effective_rate"
    default = STATE_EFFECTIVE_DEFAULTS.get(state_selected, 0.0)
    if rate_key not in st.session_state:
        st.session_state[rate_key] = float(default or 0.0)
    last_state_key = f"{key_prefix}last_state"
    last_state = st.session_state.get(last_state_key)
    if last_state != state_selected:
        st.session_state[rate_key] = float(default or 0.0)
        st.session_state[last_state_key] = state_selected
    return st.number_input("State Effective % (auto from state; editable)", min_value=0.0, max_value=15.0, step=0.1, format="%.1f", key=rate_key)

def render_year_page(year: int, key_prefix: str = ""):
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

    # Auto/Editable state effective rate
    state_rate = _state_rate_input(key_prefix, state_selected)

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
    scorp_k1_ordinary = st.sidebar.number_input("S-Corp K-1 Ordinary", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}sk1")
    k1_ordinary = st.sidebar.number_input("Partnership/Other K-1 Ordinary", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}k1")
    rental_net = st.sidebar.number_input("Rental Real Estate Net (Sch E)", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}rent")

    # Owner W-2 (S-Corp) optional include
    owner_w2_scorp = st.sidebar.number_input("Owner W-2 (S-Corp)", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}owner_w2")
    include_owner_w2 = st.sidebar.checkbox("Include Owner W-2 in baseline", value=False, key=f"{key_prefix}owner_w2_include")

    # Aggregate for current engine (ordinary rates only for now)
    biz_inc = se_income + scorp_k1_ordinary + k1_ordinary + rental_net
    other_inc = interest_inc + div_ordinary + stcg + div_qualified + ltcg
    wages_effective = wages + (owner_w2_scorp if include_owner_w2 else 0.0)

    st.sidebar.subheader("Adjustments & Deductions")
    adj = st.sidebar.number_input("Above-the-line Adjustments", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}adj")
    use_std = st.sidebar.checkbox("Use Standard Deduction", value=True, key=f"{key_prefix}use_std")
    itemized = 0.0
    if not use_std:
        itemized = st.sidebar.number_input("Itemized Deductions", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}item")

    st.sidebar.subheader("Pre-Strategy Retirement (optional)")
    pre_401k = st.sidebar.number_input("Employee 401(k) Deferral (traditional)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}401k")
    pre_ira = st.sidebar.number_input("Traditional IRA Contribution", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}ira")

    # Payments & Withholding
    st.sidebar.subheader("Payments & Withholding")
    fed_withhold = st.sidebar.number_input("Federal Withholding (W-2/1099)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}fed_wh")
    fed_est = st.sidebar.number_input("Federal Estimated Payments", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}fed_est")
    st_withhold = st.sidebar.number_input("State Withholding", min_value=0.0, value=0.0, step=250.0, key=f"{key_prefix}st_wh")
    st_est = st.sidebar.number_input("State Estimated Payments", min_value=0.0, value=0.0, step=250.0, key=f"{key_prefix}st_est")

    # Engagement, ROI & Fee Options
    st.sidebar.subheader("Engagement & ROI")
    planning_fee = st.sidebar.number_input("Client Plan Fee ($)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}fee")
    other_invest = st.sidebar.number_input("Other Investment", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}otherinv")
    exp_return_pct = st.sidebar.number_input("Expected Annual Return %", min_value=0.0, max_value=50.0, value=0.0, step=0.1, format="%.1f", key=f"{key_prefix}retpct")
    proj_years = st.sidebar.number_input("Projection Years", min_value=1, max_value=50, value=1, step=1, key=f"{key_prefix}years")

    st.sidebar.subheader("Fee Options (for PDF display)")
    success_fee_pct = st.sidebar.number_input("Option B: Success Fee % of Savings", min_value=0.0, max_value=100.0, value=20.0, step=1.0, key=f"{key_prefix}fee_succ_pct")
    hybrid_fixed = st.sidebar.number_input("Option C: Hybrid Fixed ($)", min_value=0.0, value=max(0.0, planning_fee/2), step=250.0, key=f"{key_prefix}fee_hybrid_fixed")
    hybrid_pct = st.sidebar.number_input("Option C: Hybrid % of Savings", min_value=0.0, max_value=100.0, value=10.0, step=1.0, key=f"{key_prefix}fee_hybrid_pct")

    # Build inputs
    inputs = TaxInputs(
        filing_status=filing_status,
        tax_year=year,
        wages_w2=wages_effective,
        business_income=biz_inc,
        other_income=other_inc,
        adjustments=adj,
        itemized_deductions=itemized,
        use_standard_deduction=use_std,
        state_effective_rate_pct=state_rate,
        employee_401k_deferral=pre_401k,
        traditional_ira_contribution=pre_ira,
        fed_withholding=fed_withhold,
        fed_estimated=fed_est,
        state_withholding=st_withhold,
        state_estimated=st_est,
    )

    base = compute_baseline(inputs)

    # Top metrics
    mcols = st.columns(6)
    mcols[0].metric("AGI", f"${base.agi:,.2f}")
    mcols[1].metric("Taxable Income", f"${base.taxable_income:,.2f}")
    mcols[2].metric("Federal Tax", f"${base.federal_tax:,.2f}")
    mcols[3].metric("State Tax", f"${base.state_tax:,.2f}")
    mcols[4].metric("Total Tax", f"${base.total_tax:,.2f}")
    mcols[5].metric("Marginal Rate", f"{int(base.marginal_rate*100)}%")

    pcols = st.columns(6)
    pcols[0].metric("Fed Payments", f"${base.federal_payments:,.2f}")
    pcols[1].metric("Fed Balance", ("DUE " if base.federal_balance_due>0 else "REFUND ") + f"${abs(base.federal_balance_due):,.2f}")
    pcols[2].metric("State Payments", f"${base.state_payments:,.2f}")
    pcols[3].metric("State Balance", ("DUE " if base.state_balance_due>0 else "REFUND ") + f"${abs(base.state_balance_due):,.2f}")
    pcols[4].metric("All Payments", f"${base.total_payments:,.2f}")
    pcols[5].metric("Combined", ("DUE " if base.combined_balance_due>0 else "REFUND ") + f"${abs(base.combined_balance_due):,.2f}")

    st.divider()

    # Strategies
    st.subheader(f"Strategies — {year}")
    st.caption("Current engine treats all income at ordinary rates.")
    strategy_results: List[StrategyResult] = []
    oilgas_invest = 0.0  # from Oil & Gas strategy, used in ROI

    with st.expander("Augusta Rule (§280A(g))"):
        c1, c2, c3 = st.columns([1,1,2])
        with c1:
            aug_rate = st.number_input("Fair Market Daily Rate ($)", min_value=0.0, value=0.0, step=50.0, key=f"{key_prefix}aug_rate")
        with c2:
            aug_days = st.number_input("Days (max 14)", min_value=0, max_value=14, value=0, step=1, key=f"{key_prefix}aug_days")
        with c3:
            st.caption("Rent personal residence to your business up to 14 days/year.")
        if (aug_rate > 0) and (aug_days > 0):
            strategy_results.append(strat_augusta_rule(base, inputs, aug_rate, int(aug_days)))

    with st.expander("Section 179 (Accelerated Expensing)"):
        s1, s2 = st.columns(2)
        with s1:
            eq_cost = st.number_input("Qualified Equipment Cost", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}179_cost")
        with s2:
            elect_179 = st.number_input("Elect §179 Amount", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}179_elect")
        if elect_179 > 0:
            strategy_results.append(strat_section_179(base, inputs, eq_cost, elect_179))

    with st.expander("Oil & Gas (Intangible Drilling Costs)"):
        og1, og2 = st.columns(2)
        with og1:
            oilgas_amount = st.number_input("Investment Amount ($)", min_value=0.0, value=0.0, step=5000.0, key=f"{key_prefix}og_amt")
        with og2:
            idc_pct = st.number_input("IDC Deductible %", min_value=0.0, max_value=100.0, value=80.0, step=5.0, key=f"{key_prefix}og_pct")
        st.caption("Immediate deduction of the IDC portion (planning estimate).")
        if oilgas_amount > 0 and idc_pct > 0:
            oilgas_invest = oilgas_amount
            strategy_results.append(strat_oil_gas_idc(base, inputs, oilgas_amount, idc_pct))

    with st.expander("Captive Insurance (§831(b))"):
        c1, c2 = st.columns(2)
        with c1:
            premium = st.number_input("Annual Premium (modeled deductible)", min_value=0.0, value=0.0, step=10000.0, key=f"{key_prefix}cap_prem")
        with c2:
            cap = st.number_input("§831(b) Annual Limit", min_value=500000.0, max_value=5000000.0, value=2900000.0, step=50000.0, key=f"{key_prefix}cap_limit")
        if premium > 0:
            strategy_results.append(strat_captive_831b(base, inputs, premium, cap))

    with st.expander("Additional Employee Retirement Deferral"):
        plan = st.selectbox("Plan Type", ["401(k)", "403(b)", "457(b)", "Simple IRA"], index=0, key=f"{key_prefix}plan")
        addl_def = st.number_input("Additional Pre-tax Contribution", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}addl_def")
        if addl_def > 0:
            strategy_results.append(strat_employee_deferral(base, inputs, plan, addl_def))

    # --------- Totals / ROI ----------
    total_fed = sum(s.federal_tax_savings for s in strategy_results)
    total_state = sum(s.state_tax_savings for s in strategy_results)
    total_all = sum(s.total_savings for s in strategy_results)
    total_delta_taxable = sum(s.change_in_taxable_income for s in strategy_results)  # negative lowers taxable

    after_taxable_income = max(0.0, base.taxable_income + total_delta_taxable)
    after_total_tax = max(0.0, base.total_tax - total_all)  # subtract combined savings
    after_combined_balance = round(after_total_tax - base.total_payments, 2)

    tcols = st.columns(4)
    tcols[0].metric("Federal Savings", f"${total_fed:,.2f}")
    tcols[1].metric("State Savings", f"${total_state:,.2f}")
    tcols[2].metric("Total Savings", f"${total_all:,.2f}")
    tcols[3].metric("Δ Taxable Income", f"${total_delta_taxable:,.2f}")

    # ROI (uses Oil & Gas investment + Other Investment)
    principal = oilgas_invest + other_invest
    rate = exp_return_pct / 100.0
    fv = principal * ((1 + rate) ** proj_years)
    projected_investment_gain = max(0.0, fv - principal)
    total_costs = planning_fee + principal
    total_gain = total_all + projected_investment_gain
    roi_pct = (total_gain / total_costs * 100.0) if total_costs > 0 else None

    rcols = st.columns(6)
    rcols[0].metric("Planning Fee", f"${planning_fee:,.2f}")
    rcols[1].metric("Oil & Gas Principal", f"${oilgas_invest:,.2f}")
    rcols[2].metric("Other Investment", f"${other_invest:,.2f}")
    rcols[3].metric("Proj. Return %", f"{exp_return_pct:.1f}%")
    rcols[4].metric("Proj. Investment Gain", f"${projected_investment_gain:,.2f}")
    rcols[5].metric("ROI %", f"{roi_pct:,.2f}%" if roi_pct is not None else "—")

    st.markdown("---")

    # Strategy cards (optional visual)
    if strategy_results:
        for s in strategy_results:
            with st.container(border=True):
                st.markdown(f"**{s.name}** — {s.description}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Δ Taxable", f"${s.change_in_taxable_income:,.2f}")
                c2.metric("Federal", f"${s.federal_tax_savings:,.2f}")
                c3.metric("State", f"${s.state_tax_savings:,.2f}")
                c4.metric("Total", f"${s.total_savings:,.2f}")
    else:
        st.info("No strategies added yet — exports & PDF are still available below.")

    # ----------------- Export (ALWAYS visible) -----------------
    st.markdown("### Export")
    import pandas as pd
    df = pd.DataFrame([{
        "Strategy": s.name,
        "Description": s.description,
        "Delta Taxable": s.change_in_taxable_income,
        "Federal Savings": s.federal_tax_savings,
        "State Savings": s.state_tax_savings,
        "Total Savings": s.total_savings,
        "Notes": s.notes or "",
    } for s in strategy_results])
    csv_buf = io.StringIO(); df.to_csv(csv_buf, index=False)
    st.download_button("Download CSV", csv_buf.getvalue(), file_name=f"strategy_savings_{year}.csv", mime="text/csv")

    snapshot = {
        "version": "v7.7.1",
        "year": year,
        "client": {"name": client_name, "id": client_id, "preparer": preparer, "notes": notes_meta, "state": state_selected},
        "engagement": {
            "planning_fee": planning_fee, "oil_gas": oilgas_invest, "other_invest": other_invest,
            "expected_return_pct": exp_return_pct, "years": int(proj_years),
            "fee_options": {
                "option_a_fixed": planning_fee,
                "option_b_success_pct": success_fee_pct,
                "option_c_hybrid_fixed": hybrid_fixed,
                "option_c_hybrid_pct": hybrid_pct,
            }
        },
        "income_breakdown": {
            "w2": wages,
            "owner_w2_scorp": owner_w2_scorp,
            "owner_w2_included_in_baseline": include_owner_w2,
            "interest": interest_inc,
            "dividends_ordinary": div_ordinary,
            "dividends_qualified": div_qualified,
            "short_term_gains": stcg,
            "long_term_gains": ltcg,
            "schedule_c": se_income,
            "scorp_k1_ordinary": scorp_k1_ordinary,
            "k1_ordinary": k1_ordinary,
            "rental_net": rental_net,
        },
        "payments": {
            "federal_withholding": fed_withhold, "federal_estimated": fed_est,
            "state_withholding": st_withhold, "state_estimated": st_est,
            "federal_total": base.federal_payments, "state_total": base.state_payments, "all_payments": base.total_payments,
        },
        "inputs": asdict(inputs),
        "baseline": asdict(base),
        "strategies": [asdict(s) for s in strategy_results],
        "summary": {
            "taxable_before": base.taxable_income,
            "taxable_after": after_taxable_income,
            "total_tax_before": base.total_tax,
            "total_tax_after": after_total_tax,
            "amount_owed_before": base.combined_balance_due,
            "amount_owed_after": after_combined_balance,
            "total_savings": total_all,
            "projected_investment_gain": projected_investment_gain,
            "roi_percent": roi_pct,
        }
    }
    st.download_button("Download JSON Snapshot", data=json.dumps(snapshot, indent=2),
                       file_name=f"amatore_tax_planner_{year}_snapshot.json", mime="application/json")

    # ----------------- Simple PDF (ALWAYS visible) -----------------
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import inch

        # Fee option computed amounts:
        option_a_fixed = planning_fee
        option_b_amt = (success_fee_pct/100.0) * total_all
        option_c_amt = hybrid_fixed + (hybrid_pct/100.0) * total_all

        pdf_bytes = io.BytesIO()
        c = rl_canvas.Canvas(pdf_bytes, pagesize=letter)
        width, height = letter
        y = height - 1.0*inch

        def line(txt, size=10, bold=False, dy=0.18):
            nonlocal y
            if bold:
                c.setFont("Helvetica-Bold", size)
            else:
                c.setFont("Helvetica", size)
            c.drawString(1.0*inch, y, txt)
            y -= dy*inch
            if y < 1.0*inch:
                c.showPage()
                y = height - 1.0*inch

        # Header
        line(f"Amatore & Co — Client Tax Planning Summary ({year})", size=14, bold=True, dy=0.30)
        line(f"Client: {client_name or '—'}    File#: {client_id or '—'}    Preparer: {preparer or '—'}    State: {state_selected}", dy=0.22)
        if notes_meta:
            line(f"Notes: {notes_meta[:100]}", dy=0.22)

        # Strategies (brief)
        line("Recommended Strategies", size=12, bold=True, dy=0.24)
        if strategy_results:
            for s in strategy_results:
                brief = (s.description or "").strip()
                brief = brief if len(brief) <= 110 else brief[:107] + "…"
                line(f"• {s.name}: {brief}", dy=0.18)
        else:
            line("• (None added yet)", dy=0.18)

        # Taxable Income Before/After
        line("Taxable Income", size=12, bold=True, dy=0.24)
        line(f"Before Strategies: ${base.taxable_income:,.2f}", dy=0.18)
        line(f"After  Strategies: ${after_taxable_income:,.2f}", dy=0.22)

        # Amount Owed Before/After (uses your payments/withholding)
        line("Amount Owed (or Refund if negative)", size=12, bold=True, dy=0.24)
        line(f"Before Strategies: ${base.combined_balance_due:,.2f}", dy=0.18)
        line(f"After  Strategies: ${after_combined_balance:,.2f}", dy=0.22)

        # ROI
        line("Return on Investment (ROI)", size=12, bold=True, dy=0.24)
        line(f"Planning Fee: ${planning_fee:,.2f}", dy=0.18)
        line(f"Projected Investment Gain (on ${oilgas_invest+other_invest:,.2f} @ {exp_return_pct:.1f}% for {int(proj_years)} yrs): "
             f"${projected_investment_gain:,.2f}", dy=0.18)
        line(f"Tax Savings from Strategies: ${total_all:,.2f}", dy=0.18)
        line(f"ROI %: {(roi_pct or 0.0):,.2f}%", dy=0.22)

        # Fee Options
        line("Fee Options", size=12, bold=True, dy=0.24)
        line(f"Option A — Fixed: ${option_a_fixed:,.2f}", dy=0.18)
        line(f"Option B — Success Fee ({success_fee_pct:.0f}% of savings): ${option_b_amt:,.2f}", dy=0.18)
        line(f"Option C — Hybrid: ${hybrid_fixed:,.2f} + {hybrid_pct:.0f}% of savings = ${option_c_amt:,.2f}", dy=0.22)

        # Footer small print
        line("Planning-only estimates; not tax advice. Savings modeled at ordinary rates; state rate is an effective planning rate.", size=8, dy=0.18)

        c.showPage()
        c.save(); pdf_bytes.seek(0)
        st.download_button("Download Client PDF (Simple Summary)", data=pdf_bytes,
                           file_name=f"Amatore_Tax_Summary_Simple_{year}.pdf", mime="application/pdf")
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
with st.expander("Future Enhancements (v7.8)"):
    st.markdown(
        """
        - Preferential LTCG/qualified-dividends module per year.
        - QBI (§199A) interactions; owner-comp optimization.
        - Cost seg & bonus depreciation modeling.
        - Quarter-by-quarter estimates & safe harbor checks.
        """
    )
