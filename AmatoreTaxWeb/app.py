import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime
import tempfile
import matplotlib.pyplot as plt

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

# Your tax engine
from tax_calculator import Inputs, compute_baseline, compute_scenario

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")
LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)
st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v7.0")
st.caption("Way More Money, Way Less Taxes")

# -------------------- STRATEGIES CATALOG --------------------
strategy_catalog = {
    "Augusta Rule": {
        "type": "custom_augusta",
        "desc": "Tax-free home rental to your entity up to 14 days/year; entity deducts FMV rent.",
        "irs": [{"label":"IRC §280A(g)","url":"https://www.law.cornell.edu/uscode/text/26/280A"}],
        "actions": ["Document business purpose + minutes.", "Support FMV (3+ comps).", "Pay from entity to owner."]
    },
    "Cost Segregation": {
        "type": "deduction_sc",
        "desc": "Accelerate depreciation (often with bonus/§179).",
        "irs": [
            {"label":"IRS Cost Seg ATG","url":"https://www.irs.gov/businesses/small-businesses-self-employed/cost-segregation-audit-techniques-guide"},
            {"label":"IRC §168 (MACRS)","url":"https://www.law.cornell.edu/uscode/text/26/168"}
        ],
        "actions": ["Order benefits analysis.", "Engineer study + docs.", "File Form 3115 if needed."]
    },
    "Oil & Gas Investment": {
        "type": "deduction_sc",
        "desc": "Deductible IDCs; depletion thereafter (where eligible).",
        "irs": [
            {"label":"IRC §263(c) (IDCs)","url":"https://www.law.cornell.edu/uscode/text/26/263"},
            {"label":"Depletion §§611–613","url":"https://www.law.cornell.edu/uscode/text/26/611"}
        ],
        "actions": ["Review PPM/suitability.", "Track IDC vs tangible.", "Monitor K-1 and depletion."],
        "investment": True
    },
    "Accountable Plan": {"type":"deduction_sc","desc":"Reimburse substantiated expenses; non-taxable to recipient, deductible to business.",
                         "irs":[{"label":"Pub 463 – Travel, Gift, Car","url":"https://www.irs.gov/publications/p463"}],
                         "actions":["Written plan.","Collect receipts.","Timely reimbursements."]},
    "Equipment Leasing": {"type":"deduction_sc","desc":"Lease payments for business-use equipment are deductible.",
                          "irs":[{"label":"Pub 535 – Business Expenses","url":"https://www.irs.gov/publications/p535"}],
                          "actions":["Maintain lease.","Track business-use %."]},
    "Donor Advised Fund": {"type":"deduction_itemized","desc":"Charitable contribution via DAF; AGI limits apply.",
                           "irs":[{"label":"Pub 526 – Charitable Contributions","url":"https://www.irs.gov/publications/p526"}],
                           "actions":["Written acknowledgement.","Mind AGI limits/carryforwards."]},
    "Roth IRA Conversion": {"type":"income_increase","desc":"Convert pre-tax IRA to Roth; adds ordinary income now.",
                            "irs":[{"label":"Pub 590-A","url":"https://www.irs.gov/publications/p590a"}],
                            "actions":["Model bracket fill.","Watch IRMAA/phaseouts."]}
}

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("Client")
    client_name = st.text_input("Client Name (shown on PDF)", value="Amatore Client")

    st.header("Filing Status")
    status = st.selectbox("Status", ["MFJ", "S", "HOH"], index=0)

    st.subheader("Income Details")
    wages = st.number_input("W-2 Wages", 0, 5_000_000, 120_000, 1_000)
    schc_1099 = st.number_input("1099 / Schedule C Profit (Self-Employment)", 0, 5_000_000, 60_000, 1_000)
    scorp_k1   = st.number_input("S-Corp K-1 Income (1120S)", 0, 5_000_000, 0, 1_000)
    partner_k1 = st.number_input("Partnership/Other K-1 (1065)", 0, 5_000_000, 0, 1_000)
    qdiv_income = st.number_input("Qualified Dividends", 0, 5_000_000, 0, 500)
    odiv_income = st.number_input("Ordinary Dividends",  0, 5_000_000, 0, 500)
    int_income  = st.number_input("Interest Income",     0, 5_000_000, 0, 500)
    cap_gains   = st.number_input("Capital Gains (net)", 0, 5_000_000, 0, 1_000)
    itemized = st.number_input("Itemized Deductions (baseline)", 0, 5_000_000, 12_000, 500)

    st.header("State Tax")
    states = {
        "Ohio": 0.035, "Pennsylvania": 0.0307, "Florida": 0.0,
        "New York": 0.064, "California": 0.070, "Texas": 0.0,
        "Illinois": 0.0495, "Other (custom)": 0.050
    }
    state = st.selectbox("Select State", list(states.keys()), index=0)
    state_rate = (st.number_input("Custom State Tax Rate (%)", 0.0, 15.0, 5.0, 0.1)/100
                  if state == "Other (custom)" else states[state])

    st.header("Payments & Withholdings")
    fed_withhold = st.number_input("Federal Withholding Paid ($)", 0, 5_000_000, 15_000, 500)
    fed_estimates = st.number_input("Federal Estimated Payments ($)", 0, 5_000_000, 5_000, 500)
    st_withhold = st.number_input("State Withholding Paid ($)", 0, 5_000_000, 0, 500)
    st_estimates = st.number_input("State Estimated Payments ($)", 0, 5_000_000, 0, 500)

    st.header("Scenario Setup")
    s_elect = st.radio("S-Corp Election? (for the Schedule C activity)", ["No", "Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation if S-Corp (W-2 from S-Corp)", 0, 5_000_000, 72_000, 1_000)

    st.header("Strategies (Select & Configure)")
    chosen = st.multiselect(
        "Select strategies to model",
        list(strategy_catalog.keys()),
        default=["Augusta Rule","Accountable Plan"]
    )

    strategy_configs = {}
    for s in chosen:
        meta = strategy_catalog[s]
        st.markdown(f"**{s}** — {meta['desc']}")
        if meta["type"] == "custom_augusta":
            c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
            with c1:
                fmv_day = st.number_input("FMV / day ($)", 0, 1_000_000_000, 600, 50, key=f"fmv_{s}")
            with c2:
                days = st.number_input("Days (max 14)", 0, 14, 10, 1, key=f"days_{s}")
            amount = min(14, days) * fmv_day  # no FMV cap requested
            with c3:
                entity = st.selectbox(
                    "Entity receiving the Augusta deduction",
                    ["S-Corp (1120S)", "Partnership (1065)", "Schedule C (sole prop)", "C-Corp (1120)"],
                    key=f"aug_ent_{s}"
                )
            strategy_configs[s] = {
                "type": "custom_augusta",
                "amount": amount,
                "entity": entity,
                "fmv_day": fmv_day,
                "days": days,
                "investment": 0.0,
                "roi": 0.0
            }
        else:
            c1, c2 = st.columns([1.3, 1.7])
            with c1:
                amount = st.number_input(f"{s} amount ($)", 0, 5_000_000, 0, 500, key=f"amt_{s}")
            target_choices = ["Schedule C (reduces business profit)", "Itemized deductions (below-the-line)"] \
                             if meta["type"] != "income_increase" else ["Increase Other Income"]
            with c2:
                target = st.selectbox(
                    f"Apply {s}",
                    target_choices,
                    index=0 if meta["type"] == "deduction_sc" else 1 if meta["type"] == "deduction_itemized" else 0,
                    key=f"tgt_{s}"
                )
            invest_amt, invest_roi = 0.0, 0.0
            if meta.get("investment"):
                c3, c4 = st.columns([1.0, 1.0])
                with c3:
                    invest_amt = st.number_input(f"{s} investment ($)", 0, 5_000_000, 0, 500, key=f"inv_{s}")
                with c4:
                    invest_roi = st.number_input(f"{s} expected ROI (%)", 0.0, 100.0, 8.0, 0.5, key=f"roi_{s}") / 100
            strategy_configs[s] = {
                "type": meta["type"],
                "amount": float(amount or 0),
                "target": target,
                "investment": invest_amt,
                "roi": invest_roi
            }
        st.divider()

    st.header("Marginal Rate Modeling")
    show_theoretical = st.checkbox("Show theoretical (marginal-rate) savings", value=True)
    auto_marginal = st.checkbox("Use automatic marginal rate (recommended)", value=True)
    manual_marginal_rate = st.number_input("Manual marginal rate (%)", 0.0, 100.0, 35.0, 0.1, disabled=auto_marginal)/100
    corp_rate = st.number_input("Corporate rate for C-Corp Augusta (%)", 0.0, 100.0, 21.0, 0.1)/100

# -------------------- APPLY STRATEGIES TO BUCKETS --------------------
sched_c = schc_1099
k1_s = scorp_k1
k1_p = partner_k1
other_income_base = qdiv_income + odiv_income + int_income + cap_gains

deduct_itemized_total = 0.0
add_other_income = 0.0
augusta_entity_note = None
c_corp_aug_tax_savings = 0.0

for name, cfg in strategy_configs.items():
    amt = float(cfg.get("amount") or 0)
    typ = cfg["type"]
    if amt <= 0:
        continue
    if typ == "custom_augusta":
        ent = cfg.get("entity", "S-Corp (1120S)")
        if ent.startswith("S-Corp"):
            k1_s -= amt
            augusta_entity_note = "Applied to S-Corp (reduces K-1 income)."
        elif ent.startswith("Partnership"):
            k1_p -= amt
            augusta_entity_note = "Applied to Partnership (reduces K-1 income)."
        elif ent.startswith("Schedule C"):
            sched_c -= amt
            augusta_entity_note = "Applied to Schedule C (reduces business profit)."
        else:  # C-Corp
            c_corp_aug_tax_savings = amt * corp_rate
            augusta_entity_note = f"Applied to C-Corp (entity-level deduction; shown @ {corp_rate*100:.1f}%)."
    elif typ == "deduction_sc":
        if cfg.get("target","").startswith("Schedule"):
            sched_c -= amt
        else:
            deduct_itemized_total += amt
    elif typ == "deduction_itemized":
        deduct_itemized_total += amt
    elif typ == "income_increase":
        add_other_income += amt

itemized_base = itemized
itemized_scen = max(0.0, itemized + deduct_itemized_total)
other_income_baseline = other_income_base
other_income_scen = other_income_base + add_other_income

# -------------------- BASELINE & SCENARIO RUNS --------------------
inp_base = Inputs(status=status, wages=wages, sch_c=schc_1099, other_income=other_income_baseline, itemized=itemized_base, s_corp=False)
base = compute_baseline(inp_base)

inp_scen = Inputs(status=status, wages=wages, sch_c=sched_c, other_income=other_income_scen + k1_s + k1_p,
                  itemized=itemized_scen, s_corp=s_elect, reasonable_comp=rc)
scen = compute_scenario(inp_scen)

# -------------------- STATE TAX + TOTALS --------------------
base_state_tax = max(0.0, base["taxable_income"] * state_rate)
scen_state_tax = max(0.0, scen["taxable_income"] * state_rate)

base_fed_tax = max(0.0, base["total_tax"])
scen_fed_tax = max(0.0, scen["total_tax"])

base_total_tax = base_fed_tax + base_state_tax
scen_total_tax = scen_fed_tax + scen_state_tax

# Total income (modeled) for charts
base_total_income = wages + schc_1099 + other_income_baseline + scorp_k1 + partner_k1
scen_total_income = wages + sched_c + other_income_scen + k1_s + k1_p

# Payments → refund/due (shown separately)
total_paid = (fed_withhold + fed_estimates + st_withhold + st_estimates)
base_net_due = base_total_tax - total_paid
scen_net_due = scen_total_tax - total_paid

# Projected Savings (the number we present)
projected_savings = max(0.0, base_total_tax - scen_total_tax)

# -------------------- MARGINAL-RATE ENGINE --------------------
def combined_tax(i: Inputs) -> float:
    s = compute_scenario(i)
    return max(0.0, s["total_tax"]) + max(0.0, s["taxable_income"] * state_rate)

def marginal_rate_for_bucket(bucket: str, bump: float = 1000.0) -> float:
    """Buckets: 'SC','K1S','K1P','ITEMIZED'."""
    if bucket == "ITEMIZED":
        i0 = Inputs(status=status, wages=wages, sch_c=schc_1099, other_income=other_income_baseline,
                    itemized=itemized_base, s_corp=s_elect, reasonable_comp=rc)
        t0 = combined_tax(i0)
        i1 = Inputs(status=status, wages=wages, sch_c=schc_1099, other_income=other_income_baseline,
                    itemized=itemized_base + bump, s_corp=s_elect, reasonable_comp=rc)
        t1 = combined_tax(i1)
        return max(0.0, (t0 - t1) / bump)

    i0 = Inputs(status=status, wages=wages, sch_c=schc_1099, other_income=other_income_baseline + scorp_k1 + partner_k1,
                itemized=itemized_base, s_corp=s_elect, reasonable_comp=rc)
    t0 = combined_tax(i0)

    if bucket == "SC":
        i1 = Inputs(status=status, wages=wages, sch_c=schc_1099 + bump, other_income=other_income_baseline + scorp_k1 + partner_k1,
                    itemized=itemized_base, s_corp=s_elect, reasonable_comp=rc)
    elif bucket in ("K1S","K1P"):
        i1 = Inputs(status=status, wages=wages, sch_c=schc_1099, other_income=other_income_baseline + scorp_k1 + partner_k1 + bump,
                    itemized=itemized_base, s_corp=s_elect, reasonable_comp=rc)
    else:
        return 0.0
    t1 = combined_tax(i1)
    return max(0.0, (t1 - t0) / bump)

# Theoretical savings per strategy
per_strategy_theoretical = {}
if show_theoretical:
    for name, cfg in strategy_configs.items():
        amt = float(cfg.get("amount") or 0)
        if amt <= 0:
            per_strategy_theoretical[name] = 0.0
            continue

        if name == "Augusta Rule":
            ent = cfg.get("entity","S-Corp (1120S)")
            if "C-Corp" in ent:
                mrate = corp_rate
            elif "S-Corp" in ent:
                mrate = marginal_rate_for_bucket("K1S") if auto_marginal else manual_marginal_rate
            elif "Partnership" in ent:
                mrate = marginal_rate_for_bucket("K1P") if auto_marginal else manual_marginal_rate
            else:
                mrate = marginal_rate_for_bucket("SC")  if auto_marginal else manual_marginal_rate
            per_strategy_theoretical[name] = amt * mrate
        else:
            typ = cfg["type"]
            if typ == "deduction_sc":
                mrate = marginal_rate_for_bucket("SC") if auto_marginal else manual_marginal_rate
                per_strategy_theoretical[name] = amt * mrate
            elif typ == "deduction_itemized":
                mrate = marginal_rate_for_bucket("ITEMIZED") if auto_marginal else manual_marginal_rate
                per_strategy_theoretical[name] = amt * mrate
            elif typ == "income_increase":
                mrate = marginal_rate_for_bucket("K1S") if auto_marginal else manual_marginal_rate
                per_strategy_theoretical[name] = -amt * mrate
            else:
                per_strategy_theoretical[name] = 0.0
total_theoretical = sum(v for v in per_strategy_theoretical.values() if v > 0)

# -------------------- PER-STRATEGY (ACTUAL, one-by-one) --------------------
def tax_with_subset(active_keys):
    sc = schc_1099
    k1s = scorp_k1
    k1p = partner_k1
    it  = itemized
    oi  = other_income_base

    for k in active_keys:
        cfg = strategy_configs[k]
        amt = float(cfg.get("amount") or 0)
        if amt <= 0: 
            continue
        typ = cfg["type"]
        if typ == "custom_augusta":
            ent = cfg.get("entity","S-Corp (1120S)")
            if ent.startswith("S-Corp"):        k1s = scorp_k1 - amt
            elif ent.startswith("Partnership"): k1p = partner_k1 - amt
            elif ent.startswith("Schedule C"):  sc  = schc_1099 - amt
            else:                               ...
        elif typ == "deduction_sc":
            tgt = cfg.get("target","")
            if tgt.startswith("Schedule"):       sc = schc_1099 - amt
            else:                                it = itemized + amt
        elif typ == "deduction_itemized":
            it = itemized + amt
        elif typ == "income_increase":
            oi = other_income_base + amt

    i = Inputs(status=status, wages=wages, sch_c=sc,
               other_income=oi + k1s + k1p,
               itemized=max(0.0, it),
               s_corp=s_elect, reasonable_comp=rc)
    s = compute_scenario(i)
    return max(0.0, s["total_tax"]) + max(0.0, s["taxable_income"] * state_rate)

combined_before = base_total_tax
combined_after = scen_total_tax

per_strategy_actual = {}
for k, cfg in strategy_configs.items():
    amt = float(cfg.get("amount") or 0)
    if amt <= 0:
        per_strategy_actual[k] = 0.0
        continue
    t_with_only = tax_with_subset([k])
    per_strategy_actual[k] = max(0.0, combined_before - t_with_only)

# ---- Shapley (fair attribution) ----
def shapley_attribution(strategy_configs, n_perm=200):
    import random
    keys = [k for k,v in strategy_configs.items() if float(v.get("amount") or 0) > 0]
    if not keys:
        return {}, 0.0
    base_tax = tax_with_subset([])
    full_tax = tax_with_subset(keys)
    total_savings = max(0.0, base_tax - full_tax)

    contrib = {k: 0.0 for k in keys}
    for _ in range(n_perm):
        perm = keys[:]
        random.shuffle(perm)
        active = []
        t_prev = base_tax
        for k in perm:
            active.append(k)
            t_now = tax_with_subset(active)
            contrib[k] += max(0.0, t_prev - t_now)
            t_prev = t_now

    raw_sum = sum(contrib.values())
    if raw_sum > 0:
        scale = total_savings / raw_sum
        for k in contrib:
            contrib[k] *= scale
    return contrib, total_savings

shap_contrib, shap_total = shapley_attribution(strategy_configs, n_perm=200)

# -------------------- DISPLAY --------------------
summary_df = pd.DataFrame([
    ["Total Income",   base_total_income,     scen_total_income,     scen_total_income - base_total_income],
    ["Taxable Income", base["taxable_income"],scen["taxable_income"],scen["taxable_income"] - base["taxable_income"]],
    ["Federal Tax",    base_fed_tax,          scen_fed_tax,          scen_fed_tax - base_fed_tax],
    ["State Tax",      base_state_tax,        scen_state_tax,        scen_state_tax - base_state_tax],
    ["QBI Deduction",  base["qbi"],           scen["qbi"],           scen["qbi"] - base["qbi"]],
    ["SE Tax",         base["se_tax"],        scen["se_tax"],        scen["se_tax"] - base["se_tax"]],
    ["Total Tax (Fed + State)", base_total_tax, scen_total_tax,       scen_total_tax - base_total_tax],
    ["Net Due / Refund",        base_net_due,  scen_net_due,          scen_net_due - base_net_due]
], columns=["Metric","Baseline","Scenario","Change"]).set_index("Metric")

st.subheader("📊 Before vs After")
st.dataframe(summary_df.style.format({"Baseline":"${:,.0f}","Scenario":"${:,.0f}","Change":"${:,.0f}"}),
             use_container_width=True)

# Big headline number (TAX savings only)
st.write("---")
st.markdown(
    f"<div style='font-size:22px;'>Projected Savings (Federal + State Tax): "
    f"<b><span style='color:#1a7f37;'>${projected_savings:,.0f}</span></b></div>",
    unsafe_allow_html=True
)
if show_theoretical and total_theoretical > 0:
    st.markdown(
        f"<div style='font-size:14px;opacity:0.85;'>Theoretical (marginal-rate) savings (informational): "
        f"<b>${total_theoretical:,.0f}</b></div>",
        unsafe_allow_html=True
    )

# Refund / Due
owed_or_refund = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
owed_amt = abs(scen_net_due)
st.markdown(
    f"<div style='margin-top:8px;font-size:18px;'><b>{owed_or_refund} (after ALL payments):</b> "
    f"${owed_amt:,.0f}</div>", unsafe_allow_html=True
)
if augusta_entity_note:
    st.caption(f"Augusta modeling note: {augusta_entity_note}")

# ----- Income Chart (Total vs Taxable, before/after) -----
st.write("---")
st.subheader("Income Overview")
plt.figure(figsize=(6.6, 3.0))
labels = ["Total (Before)","Total (After)","Taxable (Before)","Taxable (After)"]
vals   = [base_total_income, scen_total_income, base["taxable_income"], scen["taxable_income"]]
plt.bar(range(len(labels)), vals, color=["#0A2647","#1F6FEB","#8B8B8B","#1a7f37"])
plt.xticks(range(len(labels)), labels, rotation=10)
plt.ylabel("Dollars ($)")
plt.title("Total vs Taxable Income (Before / After)")
plt.tight_layout()
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img1:
    plt.savefig(tmp_img1.name, format="png"); plt.close()
    st.image(tmp_img1.name, use_container_width=True)

# ----- Strategy Savings Chart (actual) -----
st.subheader("Savings by Strategy (Actual vs Baseline)")
sv_names = [k for k,v in per_strategy_actual.items() if v > 0]
sv_vals  = [per_strategy_actual[k] for k in sv_names]
if sv_names:
    plt.figure(figsize=(6.6, 3.0))
    plt.bar(range(len(sv_names)), sv_vals, color="#F4B400")
    plt.xticks(range(len(sv_names)), sv_names, rotation=20, ha="right")
    plt.ylabel("Dollars ($)")
    plt.title("Per-Strategy Savings (Actual)")
    plt.tight_layout()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img2:
        plt.savefig(tmp_img2.name, format="png"); plt.close()
        st.image(tmp_img2.name, use_container_width=True)
else:
    st.info("No positive per-strategy savings to display.")

# ----- Breakdown tables -----
st.write("---")
st.subheader("Pre- vs Post-Strategy Breakdown")

# Actual (one-by-one)
actual_rows = []
for k, v in per_strategy_actual.items():
    if float(strategy_configs.get(k, {}).get("amount") or 0) > 0:
        actual_rows.append([k, strategy_configs[k]["amount"], v])
actual_df = pd.DataFrame(actual_rows, columns=["Strategy","Amount","Actual Savings vs Baseline"])
actual_df.sort_values("Actual Savings vs Baseline", ascending=False, inplace=True)

# Shapley (fair)
shap_rows = [[k, strategy_configs[k]["amount"], shap_contrib.get(k,0.0)] for k in shap_contrib.keys()]
shap_df = pd.DataFrame(shap_rows, columns=["Strategy","Amount","Fair Share of Savings (Shapley)"])
if not shap_df.empty:
    shap_df.sort_values("Fair Share of Savings (Shapley)", ascending=False, inplace=True)

tab1, tab2 = st.tabs(["By Strategy (Actual, one-by-one)", "Fair Attribution (Shapley)"])
with tab1:
    st.caption("Each strategy measured alone vs the baseline (order matters; may not add up to total).")
    if actual_df.empty:
        st.info("No strategies entered.")
    else:
        st.dataframe(actual_df.style.format({"Amount":"${:,.0f}","Actual Savings vs Baseline":"${:,.0f}"}),
                     use_container_width=True)
with tab2:
    st.caption("Order-independent, fair share that sums to total savings (best for presentations).")
    if shap_df.empty:
        st.info("No strategies entered.")
    else:
        st.dataframe(shap_df.style.format({"Amount":"${:,.0f}","Fair Share of Savings (Shapley)":"${:,.0f}"}),
                     use_container_width=True)
        st.metric("Total Savings (adds up exactly)", f"${shap_total:,.0f}")

# -------------------- PDF --------------------
def generate_summary_pdf(
    client_name,
    base_total_tax, scen_total_tax,
    base_total_income, scen_total_income,
    base_taxable, scen_taxable,
    per_strategy_actual, scen_net_due, state, state_rate,
    strategy_configs, augusta_entity_note, c_corp_aug_tax_savings,
    show_theoretical, total_theoretical,
    income_chart_path, savings_chart_path,
    shap_df, shap_total
):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Page 1
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72, hAlign='CENTER'))
        story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Amatore & Co • Tax Planning Summary</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Client:</b> {client_name}", styles["Normal"]))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 8))

    proj = max(0.0, base_total_tax - scen_total_tax)
    story.append(Paragraph(f"<b>Projected Savings (Federal + State Tax):</b> ${proj:,.0f}", styles["Heading2"]))
    story.append(Spacer(1, 6))

    data = [
        ["", "Before", "After", "Change"],
        ["Total Income", f"${base_total_income:,.0f}", f"${scen_total_income:,.0f}", f"${scen_total_income-base_total_income:,.0f}"],
        ["Taxable Income", f"${base_taxable:,.0f}", f"${scen_taxable:,.0f}", f"${scen_taxable-base_taxable:,.0f}"],
        ["Combined Tax (Fed + State)", f"${base_total_tax:,.0f}", f"${scen_total_tax:,.0f}", f"${scen_total_tax-base_total_tax:,.0f}"],
    ]
    table = Table(data, hAlign="CENTER", colWidths=[180, 120, 120, 120])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3A59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))

    # Income chart
    if income_chart_path:
        story.append(Paragraph("<b>Total vs Taxable Income</b>", styles["Heading3"]))
        story.append(Image(income_chart_path, width=460, height=230, hAlign='CENTER'))
        story.append(Spacer(1, 6))

    # Savings chart
    if savings_chart_path:
        story.append(Paragraph("<b>Savings by Strategy (Actual)</b>", styles["Heading3"]))
        story.append(Image(savings_chart_path, width=460, height=230, hAlign='CENTER'))
        story.append(Spacer(1, 6))

    owed_or_refund_pdf = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
    owed_amt_pdf = abs(scen_net_due)
    story.append(Paragraph(f"<b>{owed_or_refund_pdf} (after all payments):</b> ${owed_amt_pdf:,.0f}", styles["Normal"]))
    story.append(Paragraph(f"<b>State selected:</b> {state} ({state_rate*100:.2f}%)", styles["Normal"]))
    if augusta_entity_note:
        story.append(Paragraph(f"<b>Augusta note:</b> {augusta_entity_note}", styles["Normal"]))
    if c_corp_aug_tax_savings > 0:
        story.append(Paragraph(
            f"Augusta applied to C-Corp: estimated entity-level corporate tax savings ~ "
            f"${c_corp_aug_tax_savings:,.0f} (not reflected in personal tax).", styles["Italic"]
        ))
    if show_theoretical and total_theoretical > 0:
        story.append(Paragraph(
            f"<b>Theoretical (marginal-rate) savings (informational):</b> ${total_theoretical:,.0f}",
            styles["Normal"]
        ))
    story.append(PageBreak())

    # Page 2 — Strategy details + Shapley
    story.append(Paragraph("<b>Strategies Used — Details & References</b>", styles["Heading1"]))
    story.append(Spacer(1, 6))

    for name, cfg in strategy_configs.items():
        amt = float(cfg.get("amount") or 0)
        if amt <= 0:
            continue
        meta = strategy_catalog.get(name, {"desc":"", "irs":[], "actions":[]})
        story.append(Paragraph(f"<b>{name}</b>", styles["Heading3"]))
        if name == "Augusta Rule":
            story.append(Paragraph(
                f"FMV/day ${cfg['fmv_day']:,.0f} × {cfg['days']} day(s) (≤14). Modeled deduction: ${amt:,.0f}.",
                styles["Normal"]
            ))
            ent = cfg.get("entity","")
            if ent: story.append(Paragraph(f"Applied to: {ent}", styles["Normal"]))
        story.append(Paragraph(meta["desc"], styles["Normal"]))
        if meta.get("irs"):
            story.append(Paragraph("<b>IRS References</b>", styles["Heading4"]))
            for ref in meta["irs"]:
                story.append(Paragraph(f"• <link href='{ref['url']}' color='blue'>{ref['label']}</link>", styles["Normal"]))
        if meta.get("actions"):
            story.append(Paragraph("<b>What to do next</b>", styles["Heading4"]))
            for step in meta["actions"]:
                story.append(Paragraph(f"• {step}", styles["Normal"]))
        act = per_strategy_actual.get(name, 0.0)
        if act > 0:
            story.append(Paragraph(
                f"<b>Estimated ACTUAL tax savings (vs. before):</b> <font color='#1a7f37'><b>${act:,.0f}</b></font>",
                styles["Normal"]
            ))
        story.append(Spacer(1, 8))

    # Shapley (fair) table
    if shap_df is not None and not shap_df.empty:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>Fair Attribution (Shapley)</b>", styles["Heading2"]))
        sh_rows = [["Strategy", "Amount", "Fair Share (Shapley)"]]
        for _, r in shap_df.iterrows():
            sh_rows.append([r["Strategy"], f"${r['Amount']:,.0f}", f"${r['Fair Share of Savings (Shapley)']:,.0f}"])
        sh_rows.append(["", "", f"Total: ${shap_total:,.0f}"])
        tbl = Table(sh_rows, hAlign="LEFT")
        tbl.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                                 ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                                 ("ALIGN",(1,1),(-1,-1),"RIGHT")]))
        story.append(tbl)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "These figures are <b>estimates</b> and may not reflect 100% accuracy if projections are changed or inputs are inaccurate.",
        styles["Italic"]
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Prepared by Amatore & Co Tax Advisors — for client planning purposes only.", styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# Save charts we already produced so the PDF can embed them
income_chart_path = tmp_img1.name if 'tmp_img1' in locals() else None
savings_chart_path = tmp_img2.name if 'tmp_img2' in locals() else None

# Build Shapley DataFrame for PDF
if shap_contrib:
    shap_rows = [[k, strategy_configs[k]["amount"], shap_contrib.get(k,0.0)] for k in shap_contrib.keys()]
    shap_df = pd.DataFrame(shap_rows, columns=["Strategy","Amount","Fair Share of Savings (Shapley)"])
    shap_df.sort_values("Fair Share of Savings (Shapley)", ascending=False, inplace=True)
else:
    shap_df = pd.DataFrame(columns=["Strategy","Amount","Fair Share of Savings (Shapley)"])

# -------------------- PDF BUTTON --------------------
if st.button("📄 Generate Client PDF Summary"):
    pdf_data = generate_summary_pdf(
        client_name,
        base_total_tax, scen_total_tax,
        base_total_income, scen_total_income,
        base["taxable_income"], scen["taxable_income"],
        per_strategy_actual, scen_net_due, state, state_rate,
        strategy_configs, augusta_entity_note, c_corp_aug_tax_savings,
        show_theoretical, total_theoretical,
        income_chart_path, savings_chart_path,
        shap_df, shap_total
    )
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"{client_name.replace(' ', '_')}_Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 • Federal + State planner v7.0. Planning tool only; confirm positions before filing.")

