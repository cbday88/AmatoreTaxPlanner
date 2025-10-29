import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime
import tempfile

# PDF + chart libs
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
import matplotlib.pyplot as plt

# Calc engine (your existing module)
from tax_calculator import Inputs, compute_baseline, compute_scenario

# -------------------- PAGE SETUP --------------------
st.set_page_config(page_title="Amatore & Co Tax Planner", page_icon="💼", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)

st.caption("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884")
st.title("Amatore & Co — Tax Planning Calculator v6.4")
st.caption("Way More Money, Way Less Taxes")

# -------------------- STRATEGY DEFINITIONS --------------------
# Strategy 'type' meanings:
#  - 'custom_augusta'  : handled specially (FMV/day * days, <=14) applied to a selected entity
#  - 'deduction_sc'    : business deduction (reduces Schedule C)
#  - 'deduction_itemized' : itemized deduction (below-the-line)
#  - 'income_increase' : increases 'other income' (e.g., Roth conversion)
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
        "type": "deduction_sc",  # model IDC as business expense in MVP
        "desc": "Deductible IDCs; depletion thereafter (where eligible).",
        "irs": [
            {"label":"IRC §263(c) (IDCs)","url":"https://www.law.cornell.edu/uscode/text/26/263"},
            {"label":"Depletion §§611–613","url":"https://www.law.cornell.edu/uscode/text/26/611"}
        ],
        "actions": ["Review PPM/suitability.", "Track IDC vs tangible.", "Monitor K-1 and depletion."],
        "investment": True
    },
    # A few common modeled deductions:
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

# -------------------- SIDEBAR INPUTS --------------------
with st.sidebar:
    st.header("Client")
    client_name = st.text_input("Client Name (shown on PDF)", value="Amatore Client")

    st.header("Filing Status")
    status = st.selectbox("Status", ["MFJ", "S", "HOH"], index=0)

    # Income
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

    # State
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

    # Payments (now split Fed/State)
    st.header("Payments & Withholdings")
    fed_withhold = st.number_input("Federal Withholding Paid ($)", 0, 5_000_000, 15_000, 500)
    fed_estimates = st.number_input("Federal Estimated Payments ($)", 0, 5_000_000, 5_000, 500)
    st_withhold = st.number_input("State Withholding Paid ($)", 0, 5_000_000, 0, 500)
    st_estimates = st.number_input("State Estimated Payments ($)", 0, 5_000_000, 0, 500)

    # Entity toggle
    st.header("Scenario Setup")
    s_elect = st.radio("S-Corp Election? (for the Schedule C activity)", ["No", "Yes"], horizontal=True) == "Yes"
    rc = st.number_input("Reasonable Compensation if S-Corp (W-2 from S-Corp)", 0, 5_000_000, 72_000, 1_000)

    # Strategies
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
            # Single Augusta input; choose entity recipient
            c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
            with c1:
                fmv_day = st.number_input("FMV / day ($)", 0, 100_000, 600, 50, key=f"fmv_{s}")
            with c2:
                days = st.number_input("Days (max 14)", 0, 14, 10, 1, key=f"days_{s}")
            amount = min(14, days) * fmv_day
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
            # Choose where typical deduction applies (business vs itemized) or income add
            default_target = "Schedule C (reduces business profit)" if meta["type"] == "deduction_sc" else \
                             "Itemized deductions (below-the-line)"
            choices = ["Schedule C (reduces business profit)", "Itemized deductions (below-the-line)"]
            with c2:
                target = st.selectbox(
                    f"Apply {s}",
                    choices if meta["type"] != "income_increase" else ["Increase Other Income"],
                    index=0 if meta["type"] == "deduction_sc" else 1,
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

# -------------------- MAP INCOME + STRATEGIES --------------------
# Start with raw buckets
sched_c = schc_1099
k1_s = scorp_k1
k1_p = partner_k1
other_income_base = qdiv_income + odiv_income + int_income + cap_gains

# Apply strategies into buckets
deduct_itemized_total = 0.0
add_other_income = 0.0
augusta_entity_note = None
c_corp_aug_tax_savings = 0.0  # informational only

for name, cfg in strategy_configs.items():
    amt = float(cfg.get("amount") or 0)
    typ = cfg["type"]

    if typ == "custom_augusta":
        ent = cfg.get("entity", "S-Corp (1120S)")
        # Apply as business deduction to the selected entity
        if ent.startswith("S-Corp"):
            k1_s -= amt
            augusta_entity_note = "Applied to S-Corp (reduces K-1 income)."
        elif ent.startswith("Partnership"):
            k1_p -= amt
            augusta_entity_note = "Applied to Partnership (reduces K-1 income)."
        elif ent.startswith("Schedule C"):
            sched_c -= amt
            augusta_entity_note = "Applied to Schedule C (reduces business profit)."
        else:  # C-Corp (1120)
            # Does not pass through to individual. Show estimated corporate tax savings @ 21% informationally.
            c_corp_aug_tax_savings = amt * 0.21
            augusta_entity_note = "Applied to C-Corp (entity-level deduction; shown as corp tax savings @ 21%)."
    elif typ == "deduction_sc":
        tgt = cfg.get("target", "")
        if tgt.startswith("Schedule"):
            sched_c -= amt
        else:
            deduct_itemized_total += amt
    elif typ == "deduction_itemized":
        deduct_itemized_total += amt
    elif typ == "income_increase":
        # e.g., Roth conversion
        add_other_income += amt

# Build final inputs
itemized_base = itemized
itemized_scen = max(0.0, itemized + deduct_itemized_total)

# Other income rolls all non-SE items + any income increases (Roth, etc.)
other_income_scen = other_income_base + add_other_income
other_income_baseline = other_income_base  # for baseline comparison

# -------------------- BASELINE & SCENARIO --------------------
# Baseline uses original buckets
inp_base = Inputs(
    status=status,
    wages=wages,
    sch_c=sched_c + 0.0 + (0.0 if deduct_itemized_total or add_other_income else 0.0) - 0.0 + (0.0),  # sched_c BEFORE strategy? No: baseline must be original schc_1099
    other_income=other_income_baseline,
    itemized=itemized_base,
    s_corp=False
)
# Fix: baseline must reflect PRE-strategy amounts
inp_base.sch_c = schc_1099
base = compute_baseline(inp_base)

# Scenario uses adjusted buckets + optional S-Corp election on Schedule C activity
inp_scen = Inputs(
    status=status,
    wages=wages,
    sch_c=sched_c,                   # after business deductions incl. Augusta to Schedule C (if chosen)
    other_income=other_income_scen + k1_s + k1_p,  # K-1s included here (after Augusta to K-1 if chosen)
    itemized=itemized_scen,
    s_corp=s_elect,
    reasonable_comp=rc
)
scen = compute_scenario(inp_scen)

# -------------------- STATE TAX (non-negative) --------------------
base_state_tax = max(0.0, base["taxable_income"] * state_rate)
scen_state_tax = max(0.0, scen["taxable_income"] * state_rate)

# -------------------- TOTALS & NET --------------------
base_fed_tax = max(0.0, base["total_tax"])
scen_fed_tax = max(0.0, scen["total_tax"])

base_total_tax = base_fed_tax + base_state_tax
scen_total_tax = scen_fed_tax + scen_state_tax

total_paid = (fed_withhold + fed_estimates + st_withhold + st_estimates)
base_net_due = base_total_tax - total_paid
scen_net_due = scen_total_tax - total_paid
net_savings = base_total_tax - scen_total_tax

# -------------------- PER-STRATEGY SAVINGS (one-by-one) --------------------
def combined_tax_with_only(key: str) -> float:
    cfg = strategy_configs[key]
    amt = float(cfg.get("amount") or 0)
    typ = cfg["type"]

    sc = schc_1099
    k1s = scorp_k1
    k1p = partner_k1
    it = itemized
    oi = other_income_base

    if typ == "custom_augusta":
        ent = cfg.get("entity","S-Corp (1120S)")
        if ent.startswith("S-Corp"):
            k1s = scorp_k1 - amt
        elif ent.startswith("Partnership"):
            k1p = partner_k1 - amt
        elif ent.startswith("Schedule C"):
            sc = schc_1099 - amt
        else:
            # C-Corp: no pass-through change to individual; skip effect
            pass
    elif typ == "deduction_sc":
        tgt = cfg.get("target", "")
        if tgt.startswith("Schedule"):
            sc = schc_1099 - amt
        else:
            it = itemized + amt
    elif typ == "deduction_itemized":
        it = itemized + amt
    elif typ == "income_increase":
        oi = other_income_base + amt

    i = Inputs(status=status, wages=wages, sch_c=sc, other_income=oi + k1s + k1p, itemized=max(0.0, it),
               s_corp=s_elect, reasonable_comp=rc)
    s = compute_scenario(i)
    fed = max(0.0, s["total_tax"])
    state = max(0.0, s["taxable_income"] * state_rate)
    return fed + state

combined_before = base_total_tax
combined_after = scen_total_tax

per_strategy_savings = {}
for k, v in strategy_configs.items():
    amt = float(v.get("amount") or 0)
    if v["type"] == "income_increase" and amt <= 0:
        per_strategy_savings[k] = 0.0
        continue
    if v["type"] != "income_increase" and amt <= 0:
        per_strategy_savings[k] = 0.0
        continue
    tax_with_only = combined_tax_with_only(k)
    per_strategy_savings[k] = max(0.0, combined_before - tax_with_only)

# -------------------- DISPLAY --------------------
summary_df = pd.DataFrame([
    ["Taxable Income", base["taxable_income"], scen["taxable_income"], scen["taxable_income"] - base["taxable_income"]],
    ["Federal Tax",    base_fed_tax,           scen_fed_tax,           scen_fed_tax - base_fed_tax],
    ["State Tax",      base_state_tax,         scen_state_tax,         scen_state_tax - base_state_tax],
    ["QBI Deduction",  base["qbi"],            scen["qbi"],            scen["qbi"] - base["qbi"]],
    ["SE Tax",         base["se_tax"],         scen["se_tax"],         scen["se_tax"] - base["se_tax"]],
    ["Total Tax (Fed + State)", base_total_tax, scen_total_tax,        scen_total_tax - base_total_tax],
    ["Net Due / Refund",        base_net_due,  scen_net_due,           scen_net_due - base_net_due]
], columns=["Metric","Baseline","Scenario","Net Tax Savings"]).set_index("Metric")

st.subheader("📊 Before vs After")
st.dataframe(
    summary_df.style.format({"Baseline":"${:,.0f}","Scenario":"${:,.0f}","Net Tax Savings":"${:,.0f}"}),
    use_container_width=True
)

owed_or_refund = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
owed_amt = abs(scen_net_due)

st.write("---")
st.markdown(
    f"<div style='font-size:20px;'>Projected Federal + State Net Tax Savings: "
    f"<b><span style='color:#1a7f37;'>${net_savings:,.0f}</span></b></div>",
    unsafe_allow_html=True
)
colA, colB = st.columns(2)
with colA:
    st.metric("Before (Fed + State)", f"${combined_before:,.0f}")
with colB:
    st.metric("After (Fed + State)", f"${combined_after:,.0f}")

st.markdown(
    f"<div style='margin-top:8px;font-size:18px;'><b>{owed_or_refund} (after ALL payments):</b> "
    f"${owed_amt:,.0f}</div>",
    unsafe_allow_html=True
)

if augusta_entity_note:
    st.caption(f"Augusta modeling note: {augusta_entity_note}")

st.write("---")

# -------------------- PDF (2 pages; centered chart; Augusta C-Corp note) --------------------
def generate_summary_pdf(client_name, combined_before, combined_after, per_strategy_savings,
                         scen_net_due, state, state_rate, strategy_configs, augusta_entity_note, c_corp_aug_tax_savings):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # ---------- PAGE 1 ----------
    if LOGO_PATH.exists():
        story.append(Image(str(LOGO_PATH), width=6.5*72, height=1.5*72, hAlign='CENTER'))
        story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Amatore & Co • Tax Planning Summary</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Client:</b> {client_name}", styles["Normal"]))
    story.append(Paragraph("4010 Boardman-Canfield Rd Unit 1A • Canfield, OH 44406 • (330) 533-0884", styles["Normal"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Normal"]))
    story.append(Spacer(1, 10))

    # Summary table
    data = [
        ["", "Before Strategies", "After Strategies", "Net Tax Savings"],
        ["Combined Tax (Federal + State)",
         f"${combined_before:,.0f}", f"${combined_after:,.0f}", f"${combined_before - combined_after:,.0f}"],
    ]
    table = Table(data, hAlign="CENTER", colWidths=[220, 120, 120, 120])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3A59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # Centered bar chart
    labels = ["Before Total", "After Total"] + [k for k, v in per_strategy_savings.items() if v > 0]
    values = [combined_before, combined_after] + [per_strategy_savings[k] for k in labels[2:]]

    plt.figure(figsize=(6.6, 3.0))
    colors_list = ["#0A2647", "#1a7f37"] + ["#F4B400"] * (len(labels) - 2)
    plt.bar(range(len(labels)), values, color=colors_list)
    plt.xticks(range(len(labels)), labels, rotation=20, ha="right")
    plt.ylabel("Dollars ($)")
    plt.title("Before vs After • Savings by Strategy")
    plt.tight_layout()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        plt.savefig(tmp.name, format="png")
        plt.close()
        story.append(Image(tmp.name, width=460, height=230, hAlign='CENTER'))
    story.append(Spacer(1, 8))

    owed_or_refund_pdf = "Estimated Refund" if scen_net_due < 0 else "Estimated Amount Due"
    owed_amt_pdf = abs(scen_net_due)
    story.append(Paragraph(f"<b>{owed_or_refund_pdf} (after all payments):</b> ${owed_amt_pdf:,.0f}", styles["Normal"]))
    story.append(Paragraph(f"<b>State selected:</b> {state} ({state_rate*100:.2f}%)", styles["Normal"]))
    if augusta_entity_note:
        story.append(Paragraph(f"<b>Augusta note:</b> {augusta_entity_note}", styles["Normal"]))
    if c_corp_aug_tax_savings > 0:
        story.append(Paragraph(
            f"Augusta applied to C-Corp: estimated entity-level corporate tax savings ~ "
            f"${c_corp_aug_tax_savings:,.0f} (@21%), not reflected in personal tax.",
            styles["Italic"]
        ))

    story.append(PageBreak())

    # ---------- PAGE 2 ----------
    story.append(Paragraph("<b>Strategies Used — Details & References</b>", styles["Heading1"]))
    story.append(Spacer(1, 6))

    for name, cfg in strategy_configs.items():
        amt = float(cfg.get("amount") or 0)
        typ = cfg["type"]
        if typ == "income_increase" and amt <= 0:
            continue
        if typ != "income_increase" and amt <= 0:
            continue

        meta = strategy_catalog.get(name, {"desc":"", "irs":[], "actions":[]})
        story.append(Paragraph(f"<b>{name}</b>", styles["Heading3"]))

        if name == "Augusta Rule" and "fmv_day" in cfg:
            story.append(Paragraph(
                f"FMV/day ${cfg['fmv_day']:,.0f} × {cfg['days']} day(s) (≤14). Modeled deduction: ${amt:,.0f}.",
                styles["Normal"]
            ))
            ent = cfg.get("entity","")
            if ent:
                story.append(Paragraph(f"Applied to: {ent}", styles["Normal"]))
        story.append(Paragraph(meta["desc"], styles["Normal"]))

        if meta.get("irs"):
            story.append(Paragraph("<b>IRS References</b>", styles["Heading4"]))
            for ref in meta["irs"]:
                story.append(Paragraph(f"• <link href='{ref['url']}' color='blue'>{ref['label']}</link>", styles["Normal"]))

        if meta.get("actions"):
            story.append(Paragraph("<b>What to do next</b>", styles["Heading4"]))
            for step in meta["actions"]:
                story.append(Paragraph(f"• {step}", styles["Normal"]))

        if meta.get("investment"):
            proj_return = (cfg.get("investment", 0) or 0) * (cfg.get("roi", 0) or 0)
            story.append(Paragraph(
                f"Investment modeled: ${cfg.get('investment', 0):,.0f} • Expected ROI: {(cfg.get('roi', 0)*100):.1f}% "
                f"(Projected return: ${proj_return:,.0f})",
                styles["Normal"]
            ))

        # Per-strategy savings line (if computed)
        est = per_strategy_savings.get(name, 0.0)
        if est > 0:
            story.append(Paragraph(
                f"<b>Estimated tax savings from this strategy (vs. before):</b> "
                f"<font color='#1a7f37'><b>${est:,.0f}</b></font>",
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
        client_name, combined_before, combined_after, per_strategy_savings,
        scen_net_due, state, state_rate, strategy_configs, augusta_entity_note, c_corp_aug_tax_savings
    )
    st.download_button(
        label="Download Tax Strategy Summary PDF",
        data=pdf_data,
        file_name=f"{client_name.replace(' ', '_')}_Tax_Summary_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

st.caption("Amatore & Co © 2025 • Federal + State planner v6.4. Planning tool only; confirm positions before filing.")
