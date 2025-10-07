import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime

from tax_calculator import Inputs, compute_baseline, compute_scenario

# ----------------- Brand/Header (safe if image missing) -----------------
LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width="stretch")
st.caption("4010 Boardman-Canfield Rd Unit 1A | Canfield, OH 44406 | (330) 533-0884")

# ----------------- App chrome -----------------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")
st.title("Amatore & Co — Tax Planning Calculator")
st.caption("Way More Money, Way Less Taxes")

# ----------------- Inputs -----------------
with st.sidebar:
    st.header("Client Inputs")
    status = st.selectbox("Filing Status", ["MFJ","S","HOH"], index=0)
    wages = st.number_input("W-2 Wages", 0, 1_000_000, 120000, 1000)
    sch_c = st.number_input("Schedule C Profit", 0, 1_000_000, 60000, 1000)
    other = st.number_input("Other Income", 0, 1_000_000, 5000, 500)
    itemized = st.number_input("Itemized Deductions", 0, 1_000_000, 12000, 500)

    st.header("Scenario")
    s_elect = st.radio("S-Corp Election?", ["No","Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation (if S-Corp)", 0, 1_000_000, 72000, 1000)

    st.header("Strategy Adjustments")
    strategy = st.selectbox(
        "Select Strategy to Model",
        ["None", "Oil & Gas Investment", "Augusta Rule", "Family Management Company", "Cost Segregation"]
    )

    strategy_adjustment = 0

    if strategy == "Oil & Gas Investment":
        st.markdown("💡 *IDC portion is often deductible in year one.*")
        investment = st.number_input("Investment Amount", 0, 1_000_000, 50000, 1000)
        deductible_pct = st.slider("Deductible Portion (%)", 0, 100, 80)
        strategy_adjustment = investment * (deductible_pct / 100)

    elif strategy == "Augusta Rule":
        st.markdown("💡 *Up to 14 days rent tax-free to owner; business deducts.*")
        days = st.number_input("Days (max 14)", 0, 14, 10, 1)
        daily_rate = st.number_input("Fair Market Daily Rate", 0, 5000, 1000, 50)
        strategy_adjustment = days * daily_rate

    elif strategy == "Family Management Company":
        st.markdown("💡 *Shift reasonable wages to children via FMC.*")
        wages_shifted = st.number_input("Wages Shifted", 0, 100000, 12000, 500)
        strategy_adjustment = wages_shifted

    elif strategy == "Cost Segregation":
        st.markdown("💡 *Accelerate depreciation on qualifying components.*")
        property_value = st.number_input("Property Value", 0, 5_000_000, 500000, 10000)
        accel_pct = st.slider("Accelerated Deduction (%)", 0, 100, 25)
        strategy_adjustment = property_value * (accel_pct / 100)

# ----------------- Apply strategy to Schedule C profit -----------------
adjusted_sch_c = max(0, sch_c - strategy_adjustment)

# ----------------- Compute baseline & scenario -----------------
inp_base = Inputs(status=status, wages=wages, sch_c=adjusted_sch_c, other_income=other, itemized=itemized, s_corp=False)
inp_scen = Inputs(status=status, wages=wages, sch_c=adjusted_sch_c, other_income=other, itemized=itemized, s_corp=s_elect, reasonable_comp=rc)

base = compute_baseline(inp_base)
scen = compute_scenario(inp_scen)

# ----------------- Results table -----------------
df = pd.DataFrame([
    ["Taxable Income", base["taxable_income"], scen["taxable_income"], scen["taxable_income"]-base["taxable_income"]],
    ["Federal Tax",    base["federal_tax"],    scen["federal_tax"],    scen["federal_tax"]-base["federal_tax"]],
    ["SE Tax",         base["se_tax"],         scen["se_tax"],         scen["se_tax"]-base["se_tax"]],
    ["QBI",            base["qbi"],            scen["qbi"],            scen["qbi"]-base["qbi"]],
    ["Total Tax",      base["total_tax"],      scen["total_tax"],      scen["total_tax"]-base["total_tax"]],
], columns=["Metric","Baseline","Scenario","Delta ($)"]).set_index("Metric")

st.subheader("📊 Baseline vs Scenario")
st.dataframe(
    df.style.format({"Baseline":"${:,.0f}","Scenario":"${:,.0f}","Delta ($)":"${:,.0f}"}),
    width="stretch"  # Streamlit's new API replaces use_container_width
)

st.write("---")
savings = base['total_tax'] - scen['total_tax']
st.metric("Projected Savings", f"${savings:,.0f}")
st.metric("Baseline Total Tax", f"${base['total_tax']:,.0f}")
st.metric("Scenario Total Tax", f"${scen['total_tax']:,.0f}")

if strategy != "None":
    st.success(f"Applied Strategy: **{strategy}** — estimated deduction impact of ${strategy_adjustment:,.0f}")

st.write("---")
st.caption("Amatore & Co • 4010 Boardman-Canfield Rd, Unit 1A, Canfield, OH 44406 • (330) 533-0884 • info@amatoreco.com")
st.caption("Simplified federal-only MVP. Validate complex cases before delivery.")

# ----------------- PDF generation -----------------
def generate_summary_pdf(base, scen, strategy, strategy_adjustment):
    """Creates a one-page PDF summary and returns it as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph("<b>Amatore & Co Tax Planning Summary</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A | Canfield OH 44406 | (330) 533-0884", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 24))

    # Strategy
    story.append(Paragraph(f"<b>Selected Strategy:</b> {strategy}", styles["Heading2"]))
    story.append(Paragraph(f"Estimated Deduction Applied: ${strategy_adjustment:,.0f}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Table
    data = [
        ["Metric", "Baseline", "Scenario", "Δ ($)"],
        ["Taxable Income", f"${base['taxable_income']:,.0f}", f"${scen['taxable_income']:,.0f}", f"${scen['taxable_income'] - base['taxable_income']:,.0f}"],
        ["Federal Tax",    f"${base['federal_tax']:,.0f}",    f"${scen['federal_tax']:,.0f}",    f"${scen['federal_tax'] - base['federal_tax']:,.0f}"],
        ["SE Tax",         f"${base['se_tax']:,.0f}",         f"${scen['se_tax']:,.0f}",         f"${scen['se_tax'] - base['se_tax']:,.0f}"],
        ["QBI",            f"${base['qbi']:,.0f}",            f"${scen['qbi']:,.0f}",            f"${scen['qbi'] - base['qbi']:,.0f}"],
        ["Total Tax",      f"${base['total_tax']:,.0f}",      f"${scen['total_tax']:,.0f}",      f"${scen['total_tax'] - base['total_tax']:,.0f}"],
    ]
    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 24))

    # Summary metric
    savings = base["total_tax"] - scen["total_tax"]
    story.append(Paragraph(f"<b>Projected Savings:</b> ${savings:,.0f}", styles["Heading2"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("This projection is for planning purposes only. Confirm all tax positions with your advisor.", styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# Button + download
if st.button("📄 Generate Client Summary PDF"):
    pdf_buffer = generate_summary_pdf(base, scen, strategy, strategy_adjustment)
    st.download_button(
        label="⬇️ Download PDF",
        data=pdf_buffer,
        file_name=f"Amatore_Tax_Summary_{strategy.replace(' ', '_')}.pdf",
        mime="application/pdf",
    )

