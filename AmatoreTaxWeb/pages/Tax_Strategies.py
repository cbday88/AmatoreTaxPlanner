# pages/Tax_Strategies.py
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Amatore & Co — Tax Strategies", page_icon="📘", layout="centered")

st.title("📘 Amatore & Co — Tax Strategies")
st.caption("Authoritative references plus client-ready handouts. These materials are for planning/education; confirm positions before filing.")

# ---------- Strategy catalog ----------
STRATEGIES = [
    {
        "key": "augusta",
        "name": "Augusta Rule (IRC §280A(g))",
        "summary": "Rent your personal residence to your business for up to 14 days per year. Income is excluded; the business deducts fair-market rent.",
        "irs_links": [
            {"label": "26 U.S.C. §280A(g) — Dwelling unit used as a residence", "url": "https://www.law.cornell.edu/uscode/text/26/280A"},
            {"label": "IRS Publication 535 — Business Expenses", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Augusta Rule - Implementation.pdf",
            "Lease Agreement.pdf",
        ],
        "notes": [
            "Document fair market rental value with at least three comps (e.g., Peerspace/Airbnb/venues).",
            "Sign a short lease between the owner and the business.",
            "Hold legitimate business meetings; keep agendas and minutes.",
            "Do not issue a 1099 to yourself; ≤ 14 rental days per year are excluded."
        ],
    },
    {
        "key": "costseg",
        "name": "Cost Segregation (MACRS/Bonus/§179)",
        "summary": "Reclassify building components into shorter recovery periods to accelerate depreciation; often paired with bonus depreciation and/or §179.",
        "irs_links": [
            {"label": "IRS Cost Segregation Audit Techniques Guide", "url": "https://www.irs.gov/businesses/small-businesses-self-employed/cost-segregation-audit-techniques-guide"},
            {"label": "26 U.S.C. §168 — MACRS", "url": "https://www.law.cornell.edu/uscode/text/26/168"},
            {"label": "26 U.S.C. §179 — Election to expense certain property", "url": "https://www.law.cornell.edu/uscode/text/26/179"},
            {"label": "Form 3115 — Change in Accounting Method", "url": "https://www.irs.gov/forms-pubs/about-form-3115"},
        ],
        "downloads": [
            "Cost Segregation-App.pdf",
            "Accelerated Depreciation_Cost Segregation Example.pdf",
            "Asset Class Examples.pdf",
        ],
        "notes": [
            "Order a benefits analysis first to estimate savings.",
            "Use an engineered study; retain invoices, drawings, and closing statements.",
            "If changing methods, file Form 3115 with the return.",
        ],
    },
    {
        "key": "fmc",
        "name": "Family Management Company (Paying Children Reasonably)",
        "summary": "Use a family LLC with EIN to pay children for bona fide services. Wages must be reasonable and documented; payroll/W-2 rules may apply.",
        "irs_links": [
            {"label": "IRS Pub. 15 (Circular E) — Employer’s Tax Guide", "url": "https://www.irs.gov/publications/p15"},
            {"label": "IRS — Family Help (children employed by parents)", "url": "https://www.irs.gov/businesses/small-businesses-self-employed/family-help"},
        ],
        "downloads": [
            "Family Management Company-White Paper.pdf",
            "Family Management Company-App.pdf",
        ],
        "notes": [
            "Track hours and tasks; keep invoices from the FMC to the operating company.",
            "Open a dedicated FMC bank account; pay by check or ACH.",
            "Run payroll and issue W-2s if required by entity type and age.",
        ],
    },
    {
        "key": "oilgas",
        "name": "Oil & Gas Investment (IDCs & Depletion)",
        "summary": "Potential current-year deduction for intangible drilling costs (IDCs) and ongoing percentage depletion where eligible.",
        "irs_links": [
            {"label": "26 U.S.C. §263(c) — Intangible drilling & development costs", "url": "https://www.law.cornell.edu/uscode/text/26/263"},
            {"label": "26 U.S.C. §§611–613 — Depletion", "url": "https://www.law.cornell.edu/uscode/text/26/611"},
            {"label": "IRS Publication 535 — Business Expenses", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Oil and Gas Investment - White Paper.pdf",
            "Oil and Gas Investment - App.pdf",
        ],
        "notes": [
            "Confirm suitability and risk tolerance; review private placement docs.",
            "Document the split of IDCs vs tangible equipment.",
            "Track depletion and K-1 reporting annually.",
        ],
    },

    # --- Add more strategies as you publish them (examples below) ---
    # {
    #     "key": "accountable_plan",
    #     "name": "Accountable Plan (Reimbursements)",
    #     "summary": "Reimburse substantiated business expenses to employees/owners tax-free under a written accountable plan.",
    #     "irs_links": [{"label": "IRS Publication 463 — Travel, Gift, Car", "url": "https://www.irs.gov/publications/p463"}],
    #     "downloads": [],
    #     "notes": ["Require timely substantiation and return of excess advances.", "Reduces W-2 wages; keep receipts."]
    # },
    # {
    #     "key": "daf_bunching",
    #     "name": "Charitable Bunching / Donor-Advised Fund",
    #     "summary": "Bunch multiple years of gifts into one year to exceed the standard deduction; use a DAF to grant over time.",
    #     "irs_links": [{"label": "IRS Charitable Contributions — Pub 526", "url": "https://www.irs.gov/publications/p526"}],
    #     "downloads": [],
    #     "notes": ["Mind AGI limits and appraisal rules for non-cash gifts."]
    # },
]

# ---------- Helpers ----------
def file_exists(fname: str) -> bool:
    return Path(fname).exists()

def render_strategy(block: dict):
    st.subheader(block["name"])
    st.write(block["summary"])

    # Authoritative IRS references
    if block.get("irs_links"):
        st.markdown("**Authoritative References**")
        for ref in block["irs_links"]:
            st.markdown(f"- [{ref['label']}]({ref['url']})")

    # Client handouts / apps (download buttons for files that exist)
    if block.get("downloads"):
        st.markdown("**Client Handouts / Apps**")
        for fname in block["downloads"]:
            if file_exists(fname):
                with open(fname, "rb") as f:
                    st.download_button(
                        label=f"Download: {fname}",
                        data=f.read(),
                        file_name=fname
                    )
            else:
                st.markdown(f"- _{fname} (file not found in repository)_")

    # Implementation notes
    if block.get("notes"):
        st.markdown("**Implementation Notes**")
        for n in block["notes"]:
            st.markdown(f"- {n}")

    st.divider()

# ---------- Quick search / filter ----------
q = st.text_input("Filter strategies by keyword (name, summary, or notes):", "")
filtered = []
q_lower = q.strip().lower()
for s in STRATEGIES:
    hay = " ".join([
        s["name"],
        s["summary"],
        " ".join([n for n in s.get("notes", [])]),
        " ".join([l["label"] for l in s.get("irs_links", [])]),
    ]).lower()
    if not q_lower or q_lower in hay:
        filtered.append(s)

if not filtered:
    st.info("No strategies matched your filter. Clear the search to see all.")
else:
    for entry in filtered:
        render_strategy(entry)

st.caption("Amatore & Co © 2025 — Planning tool only; confirm positions before filing.")
