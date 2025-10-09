import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime
import tempfile

# PDF + chart libs
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
import matplotlib.pyplot as plt

# Calc engine (your existing module)
from tax_calculator import Inputs, compute_baseline, compute_scenario

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)

st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v6.1")
st.caption("Way More Money, Way Less Taxes")

# -------------------- STRATEGY CATALOG --------------------
strategy_catalog = {
    "Augusta Rule": {
        "desc": "Up to 14 days of tax-free rental of your personal residence to your business.",
        "actions": [
            "Determine fair market daily rate (keep 3+ comps).",
            "Sign short lease between owner and business.",
            "Hold legitimate business meetings; keep agenda/minutes."
        ],
        "is_investment": False,
        "has_cap_inputs": True  # special inputs (FMV/day, days) in UI
    },
    "Cost Segregation": {
        "desc": "Accelerate depreciation by reclassifying building components to shorter lives.",
        "actions": [
            "Order benefits analysis to confirm savings.",
            "Engage engineer for study; gather closing & build docs.",
            "File Form 3115 if needed; apply bonus/MACRS."
        ],
        "is_investment": False,
        "has_cap_inputs": False
    },
    "Family Management Company": {
        "desc": "Pay reasonable wages to children via a family LLC for real services.",
        "actions": [
            "Form LLC + EIN; open bank account.",
            "Track hours/tasks; invoice operating company.",
            "Run payroll/W-2 if required; keep documentation."
        ],
        "is_investment": False,
        "has_cap_inputs": False
    },
    "Oil & Gas Investment": {
        "desc": "Deductible intangible drilling costs (IDCs) and depletion; potential cash yields.",
        "actions": [
            "Review private placement; verify suitability & risk.",
            "Document IDC allocation vs tangible equipment.",
            "Track depletion; monitor K-1 reporting."
        ],
        "is_investment": True,
        "has_cap_inputs": False
    }
}

# -------------------- SIDEBAR INPUTS --------------------
with st.sidebar:
    st.header("Client")
    client_name = st.text_input("Client Name (shown on PDF)", value="Amatore Client")

    st.header("Filing Status")
    status = st.selectbox("Status", ["MFJ", "S", "HOH"], index=0)

    # --- Income entry (granular) ---
    st.subheader("Income Details")
    wages = st.number_input("W-2 Wages", 0, 5_000_000, 120_000, 1_000)
    schc_1099 = st.number_input("1099 / Schedule C Profit (Self-Employment)", 0, 5_000_000, 60_000, 1_000)

    scorp_k1   = st.number_input("S-Corp K-1 Income (other company)", 0, 5_000_000, 0, 1_000)
    partner_k1 = st.number_input("Partnership/Other K-1 Income",      0, 5_000_000, 0, 1_000)

    qdiv_income = st.number_input("Qualified Dividends", 0, 5_000_000, 0, 500)
    odiv_income = st.number_input("Ordinary Dividends",  0, 5_000_000, 0, 500)
    int_income  = st.number_input("Interest Income",     0, 5_000_000, 0, 500)
    cap_gains   = st.number_input("Capital Gains (net)", 0, 5_000_000, 0, 1_000)

    # NOTE: Preferential rates & QBI specifics should be modeled in tax_calculator engine.
    # This UI collects the right inputs so we can wire them later without changing the app.

    # Itemized/base deductions (before strategies)
    itemized = st.number_input("Itemized Deductions (baseline)", 0, 5_000_000, 12_000, 500)

    # ----- STATE TAX -----
    st.header("State Tax")
    states = {
        "Ohio": 0.035, "Pennsylvania": 0.0307, "Florida": 0.0,
        "New York": 0.064, "California": 0.070, "Texas": 0.0,
        "Illinois": 0.0495, "Other (custom)": 0.050
    }
    state = st.selectbox("Select State", list(states.keys()), index=0)
    if state == "Other (custom)":
        state_rate = st.number_input("Custom State Tax Rate (%)", 0.0, 15.0, 5.0, 0.1) / 100
    else:
        state_rate = states[state]

    # ----- PAYMENTS -----
    st.header("Payments & Withholdings")
    withholdings = st.number_input("Federal Withholding Paid ($)", 0, 5_000_000, 15_000, 500)
    est_payments = st.number_input("Estimated Payments Made ($)", 0, 5_000_000, 5_000, 500)

    # ----- ENTITY / SCENARIO -----
    st.header("Scenario Setup")
    s_elect = st.radio("S-Corp Election? (for the Schedule C/1099 activity above)", ["No", "Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation if S-Corp (W-2 from S-Corp)", 0, 5_000_000, 72_000, 1_000)

    # ----- STRATEGIES -----
    st.header("Tax Strategies (Customize)")
    chosen = st.multiselect("Select strategies to model", list(strategy_catalog.keys()), default=["Augusta Rule"])

    strategy_configs = {}
    for s in chosen:
        meta = strategy_catalog[s]
        st.markdown(f"**{s}** — {meta['desc']}")
        # Strategy input rows
        if meta.get("has_cap_inputs", False):
            # Augusta: cap by FMV/day * days, max 14
            c1, c2, c3 = st.columns([1.4, 1.4, 1.2])
            with c1:
                fmv_day = st.number_input("FMV / day ($)", 0, 100_000, 600, 50, key=f"fmv_{s}")
            with c2:
                days = st.number_input("Days (max 14)", 0, 14, 10, 1, key=f"days_{s}")
            cap_amt = fmv_day * days  # engine cap
            with c3:
                target = st.selectbox(
                    f"Apply {s} against",
                    ["Schedule C (reduces business profit)", "Itemized deductions (below-the-line)"],
                    key=f"tgt_{s}"
                )
            # For completeness allow manual override if desired:
            amt = cap_amt
        else:
            c1, c2, c3 = st.columns([1.4, 1.4, 1.2])
            with c1:
                amt = st.number_input(f"{s} deduction ($)", 0, 5_000_000, 0, 500, key=f"amt_{s}")
            with c2:
                target = st.selectbox(
                    f"Apply {s} against",
                    ["Schedule C (reduces business profit)", "Itemized deductions (below-the-line)"],
                    key=f"tgt_{s}"
                )
        invest_amt = 0
        invest_roi = 0.0
        if meta["is_investment"]:
            with c3:
                invest_amt = st.number_input(f"{s} investment ($)", 0, 5_000_000, 0, 500, key=f"inv_{s}")
            invest_roi = st.number_input(f"{s} expected ROI (%)", 0.0, 100.0, 8.0, 0.5, key=f"roi_{s}") / 100

        strategy_configs[s] = {
            "amount": amt,
            "target": target,
            "investment": invest_amt,
            "roi": invest_roi,
            "fmv_day": fmv_day if meta.get("has_cap_inputs") else None,
            "days": days if meta.get("has_cap_inputs") else None,
        }
        st.divider()

# -------------------- MAP INCOME TO ENGINE --------------------
# For now, non-SE income rolls into other_income (engine-level QBI/CG/QualDiv modeling can be added later).
other_income = scorp_k1 + partner_k1 + qdiv_income + odiv_income + int_income + cap_gains

# Strategy effects
deduct_to_schc = sum(cfg["amount"] for cfg in strategy_configs.values()
                     if cfg["target"].startswith("Schedule C"))
deduct_to_itemized = sum(cfg["amount"] for cfg in strategy_configs.values()
                         if cfg["target"].startswith("Itemized"))

# Apply strategy effects to inputs
sch_c_baseline = schc_1099
sch_c_scenario = max(0, schc_1099 - deduct_to_schc)
itemized_base  = itemized
itemized_scen  = max(0, itemized + deduct_to_itemized)

# -------------------- BASELINE & SCENARIO --------------------
# Baseline
inp_base = Inputs(status=status, wages=wages, sch_c=sch_c_baseline, other_income=other_income,
                  itemized=itemized_base, s_corp=False)
base = compute_baseline(inp_base)

# Scenario (all strategies + optional S-corp)
inp_scen = Inputs(status=status, wages=wages, sch_c=sch_c_scenario, other_income=other_income,
                  itemized=itemized_scen, s_corp=s_elect, reasonable_comp=rc)
scen = compute_scenario(inp_scen)

# State tax (simple % of taxable income)
base_state_tax = base["taxable_income"] * state_rate
scen_state_tax = scen["taxable_income"] * state_rate

# Totals & net
base_total_tax = base["total_tax"] + base_state_tax
scen_total_tax = scen["total_tax"] + scen_state_tax
total_paid = withholdings + est_payments
base_net_due = base_total_tax - total_paid
scen_net_due = scen_total_tax - total_paid
savings_total = base_total_tax - scen_total_tax

# -------------------- PER-STRATEGY SAVINGS (one-by-one recompute) --------------------
def combined_tax_with_only(strategy_key: str) -> float:
    """Return combined (Fed+State) tax if only one strategy is applied."""
    cfg = strategy_configs[strategy_key]
    apply_sc = cfg["amount"] if cfg["target"].startswith("Schedule C") else 0
    apply_it = cfg["amount"] if cfg["target"].startswith("Itemized") else 0

    sc_alone = max(0, schc_1099 - apply_sc)
    it_alone = max(0, itemized + apply_it)

    i = Inputs(status=status, wages=wages, sch_c=sc_alone, other_income=other_income,
               itemized=it_alone, s_corp=s_elect, reasonable_comp=rc)
    s = compute_scenario(i)
    state_tax = s["taxable_income"] * state_rate
    return s["total_tax"] + state_tax

combined_before = base_total_tax
combined_after  = scen_total_tax

per_strategy_savings = {}
for key, cfg in strategy_configs.items():
    if cfg["amount"] > 0:
        tax_with_only = combined_tax_with_only(key)
        per_strategy_savings[key] = max(0, combined_before - tax_with_only)  # don’t show negatives
    else:
        per_strategy_savings[key] = 0

# -------------------- DISPLAY --------------------
summary_df = pd.DataFrame([
    ["Taxable Income", base["taxable_income"], scen["taxable_income"], scen["taxable_income"] - base["taxable_income"]],
    ["Federal Tax",    base["total_tax"],     scen["total_tax"],     scen["total_tax"] - base["total_tax"]],
    ["State Tax",      base_state_tax,        scen_state_tax,        scen_state_tax - base_state_tax],
    ["QBI Deduction",  base["qbi"],           scen["qbi"],           scen["qbi"] - base["qbi"]],
    ["SE Tax",         base["se_tax"],        scen["se_tax"],        scen["se_tax"] - base["se_tax"]],
    ["Total Tax (Fed + State)", base_total_tax, scen_total_tax,      scen_total_tax - base_total_tax],
    ["Net Due / Refund",        base_net_due,  scen_net_due,         scen_net_due - base_net_due]
], columns=["Metric","Baseline","Scenario","Δ ($)"]).set_index("Metric")

st.subheader("📊 Baseline vs Scenario")
st.dataframe(
    summary_df.style.format({"Baseline":"${:,.0f}","Scenario":"${:,.0f}","Δ ($)":"${:,.0f}"}),
    use_container_width=True
)

# Savings (green), plus Estimated Due/Refund text for the scenario
owed_or_refund = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
owed_amt = abs(scen_net_due)

st.write("---")
st.markdown(
    f"<div style='font-size:20px;'>Projected Federal + State Savings: "
    f"<b><span style='color:#1a7f37;'>${savings_total:,.0f}</span></b></div>",
    unsafe_allow_html=True
)
colA, colB = st.columns(2)
with colA:
    st.metric("Baseline Total Tax (Fed + State)", f"${base_total_tax:,.0f}")
with colB:
    st.metric("Scenario Total Tax (Fed + State)", f"${scen_total_tax:,.0f}")

st.markdown(
    f"<div style='margin-top:8px;font-size:18px;'><b>{owed_or_refund} (after payments):</b> "
    f"${owed_amt:,.0f}</div>",
    unsafe_allow_html=True
)
st.write("---")

# -------------------- PDF GENERATION --------------------
def generate_summary_pdf(client_name, combined_before, combined_after, per_strategy_savings,
                         base_net_due, scen_net_due, state, state_rate, strategy_configs):
    """Branded one-pager with BEFORE/AFTER + per-strategy savings, ROI for investments, and action steps."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Header
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72))
        story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Amatore & Co • Tax Planning Summary</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Client:</b> {client_name}", styles["Normal"]))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 12))

    # High-level table (Before vs After)
    data = [
        ["", "Before Strategies", "After Strategies", "Savings"],
        ["Combined Tax (Federal + State)",
         f"${combined_before:,.0f}",
         f"${combined_after:,.0f}",
         f"${combined_before - combined_after:,.0f}"],
    ]
    table = Table(data, hAlign="LEFT", colWidths=[220, 120, 120, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3A59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # Chart: Before Total, After Total, then each strategy's savings as separate bars
    labels = ["Before Total", "After Total"] + [k for k, v in per_strategy_savings.items() if v > 0]
    values = [combined_before, combined_after] + [per_strategy_savings[k] for k in labels[2:]]

    plt.figure(figsize=(6.5, 3.2))
    colors_list = ["#0A2647", "#1a7f37"] + ["#F4B400"] * (len(labels) - 2)  # navy, green, golds
    plt.bar(range(len(labels)), values, color=colors_list)
    plt.xticks(range(len(labels)), labels, rotation=20, ha="right")
    plt.ylabel("Dollars ($)")
    plt.title("Before vs After • Savings by Strategy")
    plt.tight_layout()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        plt.savefig(tmp.name, format="png")
        plt.close()
        story.append(Image(tmp.name, width=460, height=230))
    story.append(Spacer(1, 8))

    # Refund / Due + state
    owed_or_refund_pdf = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
    owed_amt_pdf = abs(scen_net_due)
    story.append(Paragraph(
        f"<b>{owed_or_refund_pdf} (after payments):</b> ${owed_amt_pdf:,.0f}",
        styles["Normal"]
    ))
    story.append(Paragraph(
        f"<b>State selected:</b> {state} ({state_rate*100:.2f}%)",
        styles["Normal"]
    ))
    story.append(Spacer(1, 8))

    # Strategy detail: description, actions, and (if investment) projected ROI
    story.append(Paragraph("<b>Strategy Details & Next Steps</b>", styles["Heading2"]))
    any_strategy = False
    for name, cfg in strategy_configs.items():
        if cfg["amount"] <= 0:
            continue
        any_strategy = True
        meta = strategy_catalog[name]
        where = "Schedule C" if cfg["target"].startswith("Schedule C") else "Itemized"
        story.append(Paragraph(f"<b>{name}</b> — Applied to: {where}", styles["Normal"]))
        # Special line for Augusta showing cap inputs
        if name == "Augusta Rule" and cfg.get("fmv_day") is not None:
            story.append(Paragraph(
                f"Modeled as FMV/day ${cfg['fmv_day']:,.0f} × {cfg['days']} day(s) "
                f"(IRS cap 14 days). Deduction used: ${cfg['amount']:,.0f}.",
                styles["Normal"]
            ))
        story.append(Paragraph(meta["desc"], styles["Normal"]))
        if meta["is_investment"]:
            proj_return = cfg["investment"] * cfg["roi"] if cfg["investment"] and cfg["roi"] else 0
            story.append(Paragraph(
                f"Investment modeled: ${cfg['investment']:,.0f} • Expected ROI: {cfg['roi']*100:.1f}% "
                f"(Projected return: ${proj_return:,.0f})",
                styles["Normal"]
            ))
        # “What to do next” actions
        for step in meta["actions"]:
            story.append(Paragraph(f"• {step}", styles["Normal"]))
        # Estimated savings for this strategy
        if name in per_strategy_savings and per_strategy_savings[name] > 0:
            story.append(Paragraph(
                f"<b>Estimated tax savings from this strategy (vs. before):</b> "
                f"<font color='#1a7f37'><b>${per_strategy_savings[name]:,.0f}</b></font>",
                styles["Normal"]
            ))
        story.append(Spacer(1, 6))
    if not any_strategy:
        story.append(Paragraph("No strategies selected.", styles["Normal"]))
    story.append(Spacer(1, 8))

    # Disclosure
    story.append(Paragraph(
        "These figures are <b>estimates</b> and may not reflect 100% accuracy if projections are changed or inputs are inaccurate.",
        styles["Italic"]
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Prepared by Amatore & Co Tax Advisors — for client planning purposes only.", styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# -------------------- PDF BUTTON --------------------
if st.button("📄 Generate Client PDF Summary"):
    pdf_data = generate_summary_pdf(
        client_name,
        combined_before, combined_after, per_strategy_savings,
        base_net_due, scen_net_due,
        state, state_rate, strategy_configs
    )
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"{client_name.replace(' ', '_')}_Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 • Federal + State planner v6.1. Planning tool only; confirm positions before filing.")
