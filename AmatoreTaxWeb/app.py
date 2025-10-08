import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from tax_calculator import Inputs, compute_baseline, compute_scenario

# --- PAGE SETUP ---
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)
st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v2.0")
st.caption("Way More Money, Way Less Taxes")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("Client Inputs")
    status = st.selectbox("Filing Status", ["MFJ", "S", "HOH"], index=0)
    wages = st.number_input("W-2 Wages", 0, 1_000_000, 120000, 1000)
    sch_c = st.number_input("Schedule C Profit", 0, 1_000_000, 60000, 1000)
    other = st.number_input("Other Income", 0, 1_000_000, 5000, 500)
    itemized = st.number_input("Itemized Deductions", 0, 1_000_000, 12000, 500)

    # --- STATE SELECTION ---
    st.header("State Tax Selection")
    states = {
        "Ohio": 0.035,
        "Pennsylvania": 0.0307,
        "Florida": 0.0,
        "New York": 0.064,
        "California": 0.07,
        "Texas": 0.0,
        "Illinois": 0.0495,
        "Other": 0.05,
    }
    state = st.selectbox("Select State", list(states.keys()), index=0)
    state_rate = states[state]

    # --- WITHHOLDINGS / PAYMENTS ---
    st.header("Payments & Withholdings")
    withholdings = st.number_input("Federal Withholding Paid ($)", 0, 1_000_000, 15000, 500)
    est_payments = st.number_input("Estimated Payments Made ($)", 0, 1_000_000, 5000, 500)

    # --- SCENARIO / STRATEGIES ---
    st.header("Scenario Setup")
    s_elect = st.radio("S-Corp Election?", ["No", "Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation (if S-Corp)", 0, 1_000_000, 72000, 1000)

    st.header("Tax Strategies")
    strategies = {
        "Augusta Rule": "Allows up to 14 days of tax-free rental income by renting your home to your business.",
        "Cost Segregation": "Accelerates depreciation deductions by reclassifying building components for faster write-offs.",
        "Family Management Company": "Shifts income to family members in lower tax brackets by paying reasonable wages through a family LLC.",
        "Oil & Gas Investment": "Deducts intangible drilling costs and depletion allowances against active income."
    }
    selected_strategies = st.multiselect("Select Strategies", list(strategies.keys()), default=["Augusta Rule"])
    total_strategy_deduction = st.number_input("Total Strategy Deductions Applied ($)", 0, 1_000_000, 10000, 500)

# --- CALCULATIONS ---
inp_base = Inputs(status=status, wages=wages, sch_c=sch_c, other_income=other, itemized=itemized, s_corp=False)
inp_scen = Inputs(status=status, wages=wages, sch_c=sch_c, other_income=other, itemized=itemized - total_strategy_deduction,
                  s_corp=s_elect, reasonable_comp=rc)

base = compute_baseline(inp_base)
scen = compute_scenario(inp_scen)

# --- ADD STATE TAX CALCULATION ---
base_state_tax = base["taxable_income"] * state_rate
scen_state_tax = scen["taxable_income"] * state_rate

# --- NET TAX / REFUND CALCULATIONS ---
base_total_tax = base["total_tax"] + base_state_tax
scen_total_tax = scen["total_tax"] + scen_state_tax

base_net_due = base_total_tax - (withholdings + est_payments)
scen_net_due = scen_total_tax - (withholdings + est_payments)

# --- TABLE DISPLAY ---
df = pd.DataFrame([
    ["Taxable Income", base["taxable_income"], scen["taxable_income"], scen["taxable_income"] - base["taxable_income"]],
    ["Federal Tax", base["federal_tax"], scen["federal_tax"], scen["federal_tax"] - base["federal_tax"]],
    ["State Tax", base_state_tax, scen_state_tax, scen_state_tax - base_state_tax],
    ["SE Tax", base["se_tax"], scen["se_tax"], scen["se_tax"] - base["se_tax"]],
    ["QBI Deduction", base["qbi"], scen["qbi"], scen["qbi"] - base["qbi"]],
    ["Total Tax (Fed + State)", base_total_tax, scen_total_tax, scen_total_tax - base_total_tax],
    ["Net Due / Refund", base_net_due, scen_net_due, scen_net_due - base_net_due]
], columns=["Metric", "Baseline", "Scenario", "Delta ($)"]).set_index("Metric")

st.subheader("📊 Baseline vs Scenario")
st.dataframe(df.style.format({"Baseline": "${:,.0f}", "Scenario": "${:,.0f}", "Delta ($)": "${:,.0f}"}), use_container_width=True)

# --- METRICS SUMMARY ---
st.write("---")
st.metric("Projected Federal + State Savings", f"${base_total_tax - scen_total_tax:,.0f}")
st.metric("Baseline Total Tax (Fed + State)", f"${base_total_tax:,.0f}")
st.metric("Scenario Total Tax (Fed + State)", f"${scen_total_tax:,.0f}")
st.metric("Net Difference After Payments", f"${base_net_due - scen_net_due:,.0f}")
st.write("---")

# --- PDF GENERATION ---
def generate_summary_pdf(base, scen, base_total_tax, scen_total_tax, base_net_due, scen_net_due,
                         state, state_rate, selected_strategies, total_strategy_deduction):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Header with image
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72))
        story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Amatore & Co Tax Planning Summary</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A | Canfield OH 44406 | (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 24))

    # Strategy Summary
    story.append(Paragraph("<b>Selected Strategies:</b>", styles["Heading2"]))
    for s in selected_strategies:
        story.append(Paragraph(f"• {s}: {strategies[s]}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Total Strategy Deduction:</b> ${total_strategy_deduction:,.0f}", styles["Normal"]))
    story.append(Spacer(1, 18))

    # State info
    story.append(Paragraph(f"<b>State Selected:</b> {state} ({state_rate*100:.2f}%)", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Table
    data = [
        ["Metric", "Baseline", "Scenario", "Δ ($)"],
        ["Total Tax (Fed + State)", f"${base_total_tax:,.0f}", f"${scen_total_tax:,.0f}", f"${scen_total_tax - base_total_tax:,.0f}"],
        ["Net Due / Refund", f"${base_net_due:,.0f}", f"${scen_net_due:,.0f}", f"${scen_net_due - base_net_due:,.0f}"],
    ]
    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 24))

    # Summary line
    savings = base_total_tax - scen_total_tax
    story.append(Paragraph(f"<b>Projected Total Savings:</b> ${savings:,.0f}", styles["Heading2"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Prepared by Amatore & Co Tax Advisors — for client planning purposes only.", styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- PDF BUTTON ---
if st.button("📄 Generate Client PDF Summary"):
    pdf_data = generate_summary_pdf(base, scen, base_total_tax, scen_total_tax, base_net_due, scen_net_due,
                                    state, state_rate, selected_strategies, total_strategy_deduction)
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 | Federal + State planner MVP. Validate all cases before client delivery.")
