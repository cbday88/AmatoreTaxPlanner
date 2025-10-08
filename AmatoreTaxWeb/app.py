import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
import matplotlib.pyplot as plt
from tax_calculator import Inputs, compute_baseline, compute_scenario

# ---------- PAGE SETUP ----------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)
st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v4.0")
st.caption("Way More Money, Way Less Taxes")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("Client Inputs")
    status = st.selectbox("Filing Status", ["MFJ","S","HOH"], index=0)
    wages = st.number_input("W-2 Wages", 0, 1_000_000, 120000, 1000)
    sch_c = st.number_input("Schedule C Profit", 0, 1_000_000, 60000, 1000)
    other = st.number_input("Other Income", 0, 1_000_000, 5000, 500)
    itemized = st.number_input("Itemized Deductions", 0, 1_000_000, 12000, 500)

    # ----- STATE TAX -----
    st.header("State Tax Selection")
    states = {
        "Ohio": 0.035, "Pennsylvania": 0.0307, "Florida": 0.0,
        "New York": 0.064, "California": 0.07, "Texas": 0.0,
        "Illinois": 0.0495, "Other": 0.05
    }
    state = st.selectbox("Select State", list(states.keys()), index=0)
    if state == "Other":
        custom_state_rate = st.number_input("Custom State Tax Rate (%)", 0.0, 15.0, 5.0, 0.1) / 100
        state_rate = custom_state_rate
    else:
        state_rate = states[state]

    # ----- PAYMENTS -----
    st.header("Payments & Withholdings")
    withholdings = st.number_input("Federal Withholding Paid ($)", 0, 1_000_000, 15000, 500)
    est_payments = st.number_input("Estimated Payments Made ($)", 0, 1_000_000, 5000, 500)

    # ----- ENTITY / SCENARIO -----
    st.header("Scenario Setup")
    s_elect = st.radio("S-Corp Election?", ["No","Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation (if S-Corp)", 0, 1_000_000, 72000, 1000)

    # ----- STRATEGIES -----
    st.header("Tax Strategies & Adjustments")
    strategies = {
        "Augusta Rule": "Allows up to 14 days of tax-free rental income by renting your home to your business.",
        "Cost Segregation": "Accelerates depreciation deductions by reclassifying building components.",
        "Family Management Company": "Shifts income to family members in lower tax brackets.",
        "Oil & Gas Investment": "Deducts intangible drilling costs and depletion allowances."
    }

    selected_strategies = st.multiselect("Select Strategies", list(strategies.keys()), default=["Augusta Rule"])
    strategy_inputs = {}
    for s in selected_strategies:
        strategy_inputs[s] = st.number_input(f"{s} Deduction ($)", 0, 1_000_000, 0, 500)
    total_strategy_deduction = sum(strategy_inputs.values())

# ---------- CALCULATIONS ----------
inp_base = Inputs(status=status, wages=wages, sch_c=sch_c, other_income=other, itemized=itemized, s_corp=False)
inp_scen = Inputs(status=status, wages=wages, sch_c=sch_c, other_income=other,
                  itemized=itemized - total_strategy_deduction,
                  s_corp=s_elect, reasonable_comp=rc)

base = compute_baseline(inp_base)
scen = compute_scenario(inp_scen)

# Add state tax
base_state_tax = base["taxable_income"] * state_rate
scen_state_tax = scen["taxable_income"] * state_rate

# Totals and net due
base_total_tax = base["total_tax"] + base_state_tax
scen_total_tax = scen["total_tax"] + scen_state_tax
base_net_due = base_total_tax - (withholdings + est_payments)
scen_net_due = scen_total_tax - (withholdings + est_payments)

# ---------- TABLE ----------
df = pd.DataFrame([
    ["Taxable Income", base["taxable_income"], scen["taxable_income"], scen["taxable_income"] - base["taxable_income"]],
    ["Federal Tax", base["federal_tax"], scen["federal_tax"], scen["federal_tax"] - base["federal_tax"]],
    ["State Tax", base_state_tax, scen_state_tax, scen_state_tax - base_state_tax],
    ["SE Tax", base["se_tax"], scen["se_tax"], scen["se_tax"] - base["se_tax"]],
    ["QBI Deduction", base["qbi"], scen["qbi"], scen["qbi"] - base["qbi"]],
    ["Total Tax (Fed + State)", base_total_tax, scen_total_tax, scen_total_tax - base_total_tax],
    ["Net Due / Refund", base_net_due, scen_net_due, scen_net_due - base_net_due]
], columns=["Metric","Baseline","Scenario","Δ ($)"]).set_index("Metric")

st.subheader("📊 Baseline vs Scenario")
st.dataframe(df.style.format({"Baseline":"${:,.0f}","Scenario":"${:,.0f}","Δ ($)":"${:,.0f}"}), use_container_width=True)

st.write("---")
st.metric("Projected Federal + State Savings", f"${base_total_tax - scen_total_tax:,.0f}")
st.metric("Baseline Total Tax (Fed + State)", f"${base_total_tax:,.0f}")
st.metric("Scenario Total Tax (Fed + State)", f"${scen_total_tax:,.0f}")
st.metric("Net Difference After Payments", f"${base_net_due - scen_net_due:,.0f}")
st.write("---")

# ---------- PDF GENERATION (UPDATED V4.0) ----------
def generate_summary_pdf(base, scen, base_total_tax, scen_total_tax, base_net_due, scen_net_due,
                         state, state_rate, strategy_inputs):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # --- Header ---
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72))
        story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Amatore & Co Tax Planning Summary</b>", styles["Title"]))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A | Canfield, OH 44406 | (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 18))

    # --- Strategies ---
    story.append(Paragraph("<b>Selected Strategies and Amounts:</b>", styles["Heading2"]))
    if strategy_inputs:
        for s, amt in strategy_inputs.items():
            story.append(Paragraph(f"• {s}: ${amt:,.0f} — {strategies.get(s, '')}", styles["Normal"]))
    else:
        story.append(Paragraph("No strategies selected.", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Total Strategy Deduction:</b> ${sum(strategy_inputs.values()):,.0f}", styles["Normal"]))
    story.append(Spacer(1, 18))

    # --- State Info ---
    story.append(Paragraph(f"<b>State Selected:</b> {state} ({state_rate*100:.2f}%)", styles["Normal"]))
    story.append(Spacer(1, 12))

    # --- Tax Breakdown ---
    base_fed = base["total_tax"]
    scen_fed = scen["total_tax"]
    base_state = base["taxable_income"] * state_rate
    scen_state = scen["taxable_income"] * state_rate
    total_savings = (base_fed + base_state) - (scen_fed + scen_state)

    data = [
        ["Category", "Before Strategies", "After Strategies", "Δ ($)"],
        ["Federal Tax", f"${base_fed:,.0f}", f"${scen_fed:,.0f}", f"${scen_fed - base_fed:,.0f}"],
        ["State Tax", f"${base_state:,.0f}", f"${scen_state:,.0f}", f"${scen_state - base_state:,.0f}"],
        ["Combined (Fed + State)", f"${base_fed + base_state:,.0f}", f"${scen_fed + scen_state:,.0f}", f"${(scen_fed + scen_state) - (base_fed + base_state):,.0f}"]
    ]

    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3A59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")
    ]))
    story.append(table)
    story.append(Spacer(1, 18))

    # --- Chart (Before vs After) ---
    labels = ["Federal Tax", "State Tax", "Total Combined"]
    before_vals = [base_fed, base_state, base_fed + base_state]
    after_vals = [scen_fed, scen_state, scen_fed + scen_state]

    plt.figure(figsize=(5, 3))
    bar_width = 0.35
    x = range(len(labels))
    plt.bar(x, before_vals, width=bar_width, label="Before", color="#0A2647")
    plt.bar([p + bar_width for p in x], after_vals, width=bar_width, label="After", color="#F4B400")
    plt.xticks([p + bar_width / 2 for p in x], labels)
    plt.ylabel("Tax ($)")
    plt.title("Tax Comparison — Before vs After Strategies")
    plt.legend()
    plt.tight_layout()

    img_buffer = BytesIO()
    plt.savefig(img_buffer, format="png")
    plt.close()
    img_buffer.seek(0)
    story.append(Image(ImageReader(img_buffer), width=400, height=250))
    story.append(Spacer(1, 18))

    # --- Summary & Disclosure ---
    story.append(Paragraph(f"<b>Total Tax Savings from Strategies:</b> ${total_savings:,.0f}", styles["Heading2"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "These figures are <b>estimates</b> and may not reflect 100% accuracy if projections are changed or inputs are inaccurate.",
        styles["Italic"]
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Prepared by Amatore & Co Tax Advisors — for client planning purposes only.", styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ---------- PDF BUTTON ----------
if st.button("📄 Generate Client PDF Summary"):
    pdf_data = generate_summary_pdf(base, scen, base_total_tax, scen_total_tax,
                                    base_net_due, scen_net_due,
                                    state, state_rate, strategy_inputs)
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 | Federal + State Planner V4.0 with strategy customization and visual reporting.")
