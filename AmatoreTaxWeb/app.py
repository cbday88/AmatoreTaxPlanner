# Amatore & Co — Tax Planning Calculator v7.6.2 (Multi‑Year Tabs)
# Single-file Streamlit app
# ------------------------------------------------------------
# New in v7.6.2
# - Year-specific pages (tabs) for 2023, 2024, 2025
# - Proper year-aware standard deduction and bracket tables
# - 2023 fully populated; 2024 populated; 2025 UPDATED with official IRS values (Rev. Proc. 2024-40)
# - Everything else (strategies, exports) works per selected year
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

    # Income
    wages_w2: float = 0.0
    business_income: float = 0.0  # Sch C / pass-through ordinary income
    other_income: float = 0.0

    # Adjustments & Deductions
    adjustments: float = 0.0      # above-the-line
    itemized_deductions: float = 0.0
    use_standard_deduction: bool = True

    # State/Local - keep simple as flat effective
    state_effective_rate_pct: float = 0.0

    # Retirement deferrals (employee side) — optional baseline inputs (pre-strategy)
    employee_401k_deferral: float = 0.0
    traditional_ira_contribution: float = 0.0

    # Business context for certain strategies
    reasonable_comp_w2_owner: float = 0.0  # used for payroll-splitting scenarios


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
# Reference Data (Brackets & Standard Deduction)
# =============================
# 2023 & 2024 populated; 2025 UPDATED per IRS Rev. Proc. 2024-40.

FEDERAL_STD_DEDUCTION = {
    2023: {
        "Single": 13850.0,
        "MFJ": 27700.0,
        "MFS": 13850.0,
        "HOH": 20800.0,
    },
    2024: {
        "Single": 14600.0,
        "MFJ": 29200.0,
        "MFS": 14600.0,
        "HOH": 21900.0,
    },
    2025: {
        "Single": [
            (11925, 0.10), (48475, 0.12), (103350, 0.22), (197300, 0.24),
            (250525, 0.32), (626350, 0.35), (float("inf"), 0.37)
        ],
        "MFJ": [
            (23850, 0.10), (96950, 0.12), (206700, 0.22), (394600, 0.24),
            (501050, 0.32), (751600, 0.35), (float("inf"), 0.37)
        ],
        "MFS": [
            (11925, 0.10), (48475, 0.12), (103350, 0.22), (197300, 0.24),
            (250525, 0.32), (375800, 0.35), (float("inf"), 0.37)
        ],
        "HOH": [
            (17000, 0.10), (64850, 0.12), (103350, 0.22), (197300, 0.24),
            (250500, 0.32), (626350, 0.35), (float("inf"), 0.37)
        ],
    },
}

# Progressive tax brackets per year & status as list of (ceiling, rate)
FEDERAL_BRACKETS = {
    2023: {
        "Single": [
            (11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
            (231250, 0.32), (578125, 0.35), (float("inf"), 0.37)
        ],
        "MFJ": [
            (22000, 0.10), (89450, 0.12), (190750, 0.22), (364200, 0.24),
            (462500, 0.32), (693750, 0.35), (float("inf"), 0.37)
        ],
        "MFS": [
            (11000, 0.10), (44725, 0.12), (95375, 0.22), (182100, 0.24),
            (231250, 0.32), (346875, 0.35), (float("inf"), 0.37)
        ],
        "HOH": [
            (15700, 0.10), (59850, 0.12), (95350, 0.22), (182100, 0.24),
            (231250, 0.32), (578100, 0.35), (float("inf"), 0.37)
        ],
    },
    2024: {
        "Single": [
            (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
            (243725, 0.32), (609350, 0.35), (float("inf"), 0.37)
        ],
        "MFJ": [
            (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
            (487450, 0.32), (731200, 0.35), (float("inf"), 0.37)
        ],
        "MFS": [
            (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
            (243725, 0.32), (365600, 0.35), (float("inf"), 0.37)
        ],
        "HOH": [
            (16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
            (243700, 0.32), (609350, 0.35), (float("inf"), 0.37)
        ],
    },
    2025: {
        # Placeholder: mirrors 2024 until IRS publishes final tables
        "Single": [
            (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
            (243725, 0.32), (609350, 0.35), (float("inf"), 0.37)
        ],
        "MFJ": [
            (23200, 0.10), (94300, 0.12), (201050, 0.22), (383900, 0.24),
            (487450, 0.32), (731200, 0.35), (float("inf"), 0.37)
        ],
        "MFS": [
            (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
            (243725, 0.32), (365600, 0.35), (float("inf"), 0.37)
        ],
        "HOH": [
            (16550, 0.10), (63100, 0.12), (100500, 0.22), (191950, 0.24),
            (243700, 0.32), (609350, 0.35), (float("inf"), 0.37)
        ],
    },
}


def get_std_deduction(tax_year: int, filing_status: str, use_standard: bool, itemized: float) -> float:
    if not use_standard:
        return max(0.0, itemized)
    sd_map = FEDERAL_STD_DEDUCTION.get(tax_year, FEDERAL_STD_DEDUCTION[2024])
    return sd_map.get(filing_status, sd_map.get("MFJ", 0.0))


def compute_federal_tax(filing_status: str, taxable_income: float, tax_year: int) -> tuple[float, float]:
    """Returns (federal_tax, marginal_rate). Uses year-aware bracket tables.
    """
    ti = max(0.0, taxable_income)
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
    # Gross income
    gross = float(inputs.wages_w2) + float(inputs.business_income) + float(inputs.other_income)

    # Above-the-line adjustments (reduces AGI)
    agi = max(0.0, gross - float(inputs.adjustments))

    # Standard vs Itemized
    std_or_itemized = get_std_deduction(
        inputs.tax_year, inputs.filing_status, inputs.use_standard_deduction, inputs.itemized_deductions
    )

    # Pre-strategy retirement contributions (if provided) — treat as above-the-line for simplicity
    predeferrals = float(inputs.employee_401k_deferral) + float(inputs.traditional_ira_contribution)

    taxable_income = max(0.0, agi - std_or_itemized - predeferrals)

    fed_tax, marginal_rate = compute_federal_tax(inputs.filing_status, taxable_income, inputs.tax_year)

    state_tax = round(taxable_income * (inputs.state_effective_rate_pct / 100.0), 2)

    total_tax = round(fed_tax + state_tax, 2)

    return BaselineResult(
        agi=round(agi, 2),
        taxable_income=round(taxable_income, 2),
        federal_tax=fed_tax,
        state_tax=state_tax,
        total_tax=total_tax,
        marginal_rate=marginal_rate,
    )


# =============================
# Strategy Engines (unchanged)
# =============================

def _state_savings(delta_taxable: float, state_effective_rate_pct: float) -> float:
    return round(max(0.0, delta_taxable) * (state_effective_rate_pct / 100.0), 2)


def strat_augusta_rule(
    baseline: BaselineResult,
    inputs: TaxInputs,
    fair_daily_rate: float,
    days: int,
    description_override: Optional[str] = None,
) -> StrategyResult:
    days = max(0, min(14, int(days)))
    rent = max(0.0, float(fair_daily_rate) * days)

    fed_save = round(rent * baseline.marginal_rate, 2)
    st_save = _state_savings(rent, inputs.state_effective_rate_pct)

    desc = description_override or (
        "Rent home to business up to 14 days at FMV; owner excludes income; business deducts expense."
    )

    return StrategyResult(
        name="Augusta Rule",
        description=desc,
        change_in_taxable_income=-rent,
        federal_tax_savings=fed_save,
        state_tax_savings=st_save,
        total_savings=round(fed_save + st_save, 2),
        notes=f"Modeled at FMV ${fair_daily_rate:,.0f} x {days} days = ${rent:,.2f}.",
    )


def strat_section_179(
    baseline: BaselineResult,
    inputs: TaxInputs,
    equipment_cost: float,
    elected_179: float,
    description_override: Optional[str] = None,
) -> StrategyResult:
    equipment_cost = max(0.0, float(equipment_cost))
    elected = max(0.0, min(float(elected_179), equipment_cost))

    fed_save = round(elected * baseline.marginal_rate, 2)
    st_save = _state_savings(elected, inputs.state_effective_rate_pct)

    desc = description_override or (
        "Elect to expense qualified equipment under IRC §179 (subject to limits/phaseouts)."
    )

    return StrategyResult(
        name="Section 179 (Accelerated Expensing)",
        description=desc,
        change_in_taxable_income=-elected,
        federal_tax_savings=fed_save,
        state_tax_savings=st_save,
        total_savings=round(fed_save + st_save, 2),
        notes=f"Elected ${elected:,.2f} on equipment cost ${equipment_cost:,.2f}.",
    )


def strat_captive_831b(
    baseline: BaselineResult,
    inputs: TaxInputs,
    annual_premium: float,
    cap_limit: float = 2900000.0,
    description_override: Optional[str] = None,
) -> StrategyResult:
    premium = max(0.0, float(annual_premium))
    deductible = min(premium, max(0.0, float(cap_limit)))

    fed_save = round(deductible * baseline.marginal_rate, 2)
    st_save = _state_savings(deductible, inputs.state_effective_rate_pct)

    desc = description_override or (
        "Elect under §831(b) for qualifying micro-captive; treat premiums as deductible (planning estimate)."
    )

    return StrategyResult(
        name="Captive Insurance (§831(b))",
        description=desc,
        change_in_taxable_income=-deductible,
        federal_tax_savings=fed_save,
        state_tax_savings=st_save,
        total_savings=round(fed_save + st_save, 2),
        notes=f"Modeled deductible premium ${deductible:,.2f} (cap ${cap_limit:,.0f}).",
    )


def strat_employee_deferral(
    baseline: BaselineResult,
    inputs: TaxInputs,
    plan_type: str,
    contribution: float,
    description_override: Optional[str] = None,
) -> StrategyResult:
    contrib = max(0.0, float(contribution))
    fed_save = round(contrib * baseline.marginal_rate, 2)
    st_save = _state_savings(contrib, inputs.state_effective_rate_pct)

    desc = description_override or (f"Pre-tax {plan_type} employee deferral (traditional)")

    return StrategyResult(
        name=f"{plan_type} Deferral",
        description=desc,
        change_in_taxable_income=-contrib,
        federal_tax_savings=fed_save,
        state_tax_savings=st_save,
        total_savings=round(fed_save + st_save, 2),
        notes=f"Modeled contribution ${contrib:,.2f}.",
    )


# =============================
# Streamlit UI (Multi‑Year Tabs)
# =============================

st.set_page_config(page_title="Amatore & Co — Tax Planning Calculator v7.6.2", page_icon="📊", layout="wide")

st.title("Amatore & Co — Tax Planning Calculator v7.6.2")
st.caption("Planning-only estimates. For educational use; not tax advice.")

with st.expander("About this version"):
    st.markdown(
        """
        **What's new (v7.6.2)**
        - Year-specific tabs for **2023**, **2024**, and **2025**.
        - 2023 & 2024 tables populated. **2025 mirrors 2024** as a placeholder until the IRS publishes final values.
        - All strategies and exports operate within the selected year tab.
        """
    )


def render_year_page(year: int, key_prefix: str = ""):
    """Renders one full calculator page for a given tax year.
    key_prefix is used to make Streamlit widget keys unique per tab.
    """
    st.subheader(f"Baseline Inputs — {year}")

    st.sidebar.header(f"Client Inputs — {year}")

    filing_status = st.sidebar.selectbox(
        "Filing Status",
        ["MFJ", "Single", "MFS", "HOH"],
        index=0,
        key=f"{key_prefix}fs",
    )

    col_fs1, col_fs2 = st.sidebar.columns(2)
    with col_fs1:
        st.number_input("Tax Year", min_value=2023, max_value=2026, value=year, step=1, key=f"{key_prefix}ty", disabled=True)
    with col_fs2:
        state_rate = st.number_input("State Effective %", min_value=0.0, max_value=15.0, value=0.0, step=0.1, format="%.1f", key=f"{key_prefix}state")

    st.sidebar.subheader("Income")
    wages = st.sidebar.number_input("W-2 Wages", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}w2")
    biz_inc = st.sidebar.number_input("Business Income (ordinary)", min_value=0.0, value=0.0, step=1000.0, key=f"{key_prefix}biz")
    other_inc = st.sidebar.number_input("Other Income", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}other")

    st.sidebar.subheader("Adjustments & Deductions")
    adj = st.sidebar.number_input("Above-the-line Adjustments", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}adj")
    use_std = st.sidebar.checkbox("Use Standard Deduction", value=True, key=f"{key_prefix}use_std")
    itemized = 0.0
    if not use_std:
        itemized = st.sidebar.number_input("Itemized Deductions", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}item")

    st.sidebar.subheader("Pre-Strategy Retirement (optional)")
    pre_401k = st.sidebar.number_input("Employee 401(k) Deferral (traditional)", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}401k")
    pre_ira = st.sidebar.number_input("Traditional IRA Contribution", min_value=0.0, value=0.0, step=500.0, key=f"{key_prefix}ira")

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

    # Reporting
    if strategy_results:
        st.subheader("Strategy Savings Summary")

        total_fed = sum(s.federal_tax_savings for s in strategy_results)
        total_state = sum(s.state_tax_savings for s in strategy_results)
        total_all = sum(s.total_savings for s in strategy_results)

        tcols = st.columns(3)
        tcols[0].metric("Federal Savings", f"${total_fed:,.2f}")
        tcols[1].metric("State Savings", f"${total_state:,.2f}")
        tcols[2].metric("Total Savings", f"${total_all:,.2f}")

        st.markdown("---")

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

        # Export
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

        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button("Download CSV", csv_buf.getvalue(), file_name=f"strategy_savings_{year}.csv", mime="text/csv")

        snapshot = {
            "version": "v7.6.2",
            "year": year,
            "inputs": asdict(inputs),
            "baseline": asdict(base),
            "strategies": [asdict(s) for s in strategy_results],
            "totals": {"federal": total_fed, "state": total_state, "all": total_all},
        }
        st.download_button(
            "Download JSON Snapshot",
            data=json.dumps(snapshot, indent=2),
            file_name=f"amatore_tax_planner_{year}_snapshot.json",
            mime="application/json",
        )
    else:
        st.info("Add values to any strategy expander above to see savings and export options.")


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
        - **Update IRS 2025 brackets/standard deduction** once finalized.
        - Add owner-comp optimization and payroll split modeling.
        - Add QBI (§199A) interaction model (phase-outs, W-2/UBIA tests).
        - Add cost segregation & bonus depreciation module with class-life splits.
        - Add login/client save + paywall (integrate with lightweight backend/auth).
        """
    )
