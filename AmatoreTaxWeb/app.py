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

# Your calc engine (unchanged)
from tax_calculator import Inputs, compute_baseline, compute_scenario

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)

st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v5.2")
st.caption("Way More Money, Way Less Taxes")

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
    scorp_k1 = st.number_input("S-Corp K-1 Income", 0, 5_000_000, 0, 1_000)
    ccorp_div = st.number_input("C-Corp Dividends", 0, 5_000_000, 0, 500)
    int_income = st.number_input("Interest Income", 0, 5_000_000, 0, 500)
    div_income = st.number_input("Dividends (total)", 0, 5_000_000, 0, 500)
    cap_gains  = st.number_input("Capital Gains (net)", 0, 5_000_000, 0, 1_000)

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

    # ----- STRATEGIES (custom amount + where to apply) -----
    st.header("Tax Strategies (Customize)")
    strategy_catalog = {
        "Augusta Rule": "Up to 14 days of tax-free home rental to your business.",
        "Cost Segregation": "Accelerate depreciation by reclassifying components.",
        "Family Management Company": "Shift reasonable wages to family members.",
        "Oil & Gas Investment": "IDCs/depletion can reduce current taxable income."
    }

    chosen = st.multiselect("Select strategies to model", list(strategy_catalog.keys()), default=["Augusta Rule"])

    strategy_configs = {}
    for s in chosen:
        st.markdown(f"**{s}** — {strategy_catalog[s]}")
        col1, col2 = st.columns([2, 2])
        with col1:
            amt = st.number_input(f"{s} deduction ($)", 0, 5_000_000, 0, 500, key=f"amt_{s}")
        with col2:
            target = st.selectbox(
                f"Apply {s} against",
                ["Schedule C (reduces business profit)", "Itemized deductions (below-the-line)"],
                key=f"tgt_{s}"
            )
        strategy_configs[s] = {"amount": amt, "target": target}
        st.divider()

# -------------------- MAP NEW INCOME FIELDS TO ENGINE --------------------
other_income = scorp_k1 + ccorp_div + int_income + div_income + cap_gains

# Strategies: sum per target
deduct_to_schc = sum(cfg["amount"] for cfg in strategy_configs.values()
                     if cfg["target"].startswith("Schedule C"))
deduct_to_itemized = sum(cfg["amount"] for cfg in strategy_configs.values()
                         if cfg["target"].startswith("Itemized"))

# Apply strategy effects
sch_c_baseline = schc_1099
sch_c_scenario = max(0, schc_1099 - deduct_to_schc)
itemized_baseline = itemized
itemized_scenario = max(0, itemized + deduct_to_itemized)

# -------------------- RUN CALCULATIONS --------------------
# Baseline (no strategies, no S-Corp)
inp_base = Inputs(status=status, wages=wages, sch_c=sch_c_baseline, other_income=other_income,
                  itemized=itemized_baseline, s_corp=False)
base = compute_baseline(inp_base)

# Scenario (strategies + optional S-Corp)
inp_scen = Inputs(status=status, wages=wages, sch_c=sch_c_scenario, other_income=other_income,
                  itemized=itemized_scenario, s_corp=s_elect, reasonable_comp=rc)
scen = compute_scenario(inp_scen)

# State tax (simple % of taxable income for quick planning)
base_state_tax = base["taxable_income"] * state_rate
scen_state_tax = scen["taxable_income"] * state_rate

# Totals + net due/refund
base_total_tax = base["total_tax"] + base_state_tax
scen_total_tax = scen["total_tax"] + scen_state_tax
total_paid = withholdings + est_payments
base_net_due = base_total_tax - total_paid
scen_net_due = scen_total_tax - total_paid

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
savings = base_total_tax - scen_total_tax
owed_or_refund = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
owed_or_refund_amt = abs(scen_net_due)

st.write("---")
st.markdown(
    f"<div style='font-size:20px;'>Projected Federal + State Savings: "
    f"<b><span style='color:#1a7f37;'>${savings:,.0f}</span></b></div>",
    unsafe_allow_html=True
)
colA, colB = st.columns(2)
with colA:
    st.metric("Baseline Total Tax (Fed + State)", f"${base_total_tax:,.0f}")
with colB:
    st.metric("Scenario Total Tax (Fed + State)", f"${scen_total_tax:,.0f}")

st.markdown(
    f"<div style='margin-top:8px;font-size:18px;'><b>{owed_or_refund} (after payments):</b> "
    f"${owed_or_refund_amt:,.0f}</div>",
    unsafe_allow_html=True
)

st.write("---")

# -------------------- PDF GENERATION --------------------
def generate_summary_pdf(client_name, base, scen, base_total_tax, scen_total_tax, base_net_due, scen_net_due,
                         state, state_rate, strategy_configs):
    """Branded one-pager with chart + full breakdown + client name."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Header / Banner
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72))
        story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Amatore & Co • Tax Planning Summary</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Client:</b> {client_name}", styles["Normal"]))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 14))

    # Strategy list (with where applied)
    story.append(Paragraph("<b>Selected Strategies & Amounts</b>", styles["Heading2"]))
    if strategy_configs:
        for s, cfg in strategy_configs.items():
            where = "Schedule C" if cfg["target"].startswith("Schedule C") else "Itemized"
            story.append(Paragraph(f"• {s}: ${cfg['amount']:,.0f} — Applied to: {where}", styles["Normal"]))
    else:
        story.append(Paragraph("No strategies selected.", styles["Normal"]))
    story.append(Spacer(1, 8))

    total_strategy = sum(cfg["amount"] for cfg in strategy_configs.values())
    story.append(Paragraph(f"<b>Total strategy deductions modeled:</b> ${total_strategy:,.0f}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # State info
    story.append(Paragraph(f"<b>State selected:</b> {state} ({state_rate*100:.2f}%)", styles["Normal"]))
    story.append(Spacer(1, 14))

    # Numeric breakdown table
    base_fed = base["total_tax"]
    scen_fed = scen["total_tax"]
    base_state = base["taxable_income"] * state_rate
    scen_state = scen["taxable_income"] * state_rate
    combined_before = base_fed + base_state
    combined_after  = scen_fed + scen_state
    combined_delta  = combined_after - combined_before
    total_savings   = combined_before - combined_after

    data = [
        ["Category", "Before Strategies", "After Strategies", "Δ ($)"],
        ["Federal Tax", f"${base_fed:,.0f}", f"${scen_fed:,.0f}", f"${scen_fed - base_fed:,.0f}"],
        ["State Tax",   f"${base_state:,.0f}", f"${scen_state:,.0f}", f"${scen_state - base_state:,.0f}"],
        ["Combined (Fed + State)", f"${combined_before:,.0f}", f"${combined_after:,.0f}", f"${combined_delta:,.0f}"],
    ]
    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3A59")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))

    # Chart (save to temp file so ReportLab can load it on Streamlit Cloud)
    labels = ["Federal", "State", "Combined"]
    before_vals = [base_fed, base_state, combined_before]
    after_vals  = [scen_fed, scen_state, combined_after]

    plt.figure(figsize=(5, 3))
    bar_width = 0.35
    x = range(len(labels))
    plt.bar(list(x), before_vals, width=bar_width, label="Before", color="#0A2647")  # navy
    plt.bar([p + bar_width for p in x], after_vals, width=bar_width, label="After", color="#1a7f37")  # green
    plt.xticks([p + bar_width/2 for p in x], labels)
    plt.ylabel("Tax ($)")
    plt.title("Tax Comparison — Before vs After Strategies")
    plt.legend()
    plt.tight_layout()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        plt.savefig(tmp.name, format="png")
        plt.close()
        story.append(Image(tmp.name, width=400, height=240))
    story.append(Spacer(1, 12))

    # Savings (green) + Estimated Due/Refund line
    owed_or_refund_pdf = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
    owed_amt_pdf = abs(scen_net_due)

    story.append(Paragraph(
        f"<b>Total Tax Savings from Strategies:</b> "
        f"<font color='#1a7f37'><b>${total_savings:,.0f}</b></font>",
        styles["Heading2"]
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>{owed_or_refund_pdf} (after payments):</b> ${owed_amt_pdf:,.0f}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 10))

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
        client_name, base, scen, base_total_tax, scen_total_tax, base_net_due, scen_net_due,
        state, state_rate, strategy_configs
    )
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"{client_name.replace(' ', '_')}_Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 • Federal + State planner v5.2. Planning tool only; confirm positions before filing.")
