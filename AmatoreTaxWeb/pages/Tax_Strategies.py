import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Amatore & Co — Tax Strategies", page_icon="📘", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)

st.title("📘 Amatore & Co — Tax Strategies")
st.caption("Authoritative references + your client handouts, all in one place.")

# ---- Strategy Catalog (with IRS links for trust) ----
STRATEGIES = [
    {
        "name": "Augusta Rule (IRC §280A(g))",
        "summary": "Rent your personal residence to your business for up to 14 days per year — income excluded; business deducts FMV rent.",
        "irs_links": [
            {"label": "26 U.S. Code § 280A(g) – Dwelling unit used as a residence", "url": "https://www.law.cornell.edu/uscode/text/26/280A"},
            {"label": "IRS Publication 535 – Business Expenses (home rental context)", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Augusta Rule - Implementation.pdf",
            "Lease Agreement.pdf",
        ],
        "notes": [
            "Document business purpose (agenda/minutes), FMV (3+ comps), and payment.",
            "14-day max exclusion per calendar year; do not issue 1099-MISC to yourself."
        ]
    },
    {
        "name": "Cost Segregation (MACRS/Bonus/§179)",
        "summary": "Reclassify building components into shorter lives to accelerate depreciation; often paired with bonus and/or §179.",
        "irs_links": [
            {"label": "IRS Cost Segregation Audit Techniques Guide", "url": "https://www.irs.gov/businesses/small-businesses-self-employed/cost-segregation-audit-techniques-guide"},
            {"label": "26 U.S. Code § 168 – MACRS", "url": "https://www.law.cornell.edu/uscode/text/26/168"},
            {"label": "26 U.S. Code § 179 – Election to expense certain depreciable assets", "url": "https://www.law.cornell.edu/uscode/text/26/179"},
            {"label": "Form 3115 – Change in Accounting Method", "url": "https://www.irs.gov/forms-pubs/about-form-3115"},
        ],
        "downloads": [
            "Cost Segregation-App.pdf",
            "Accelerated Depreciation_Cost Segregation Example.pdf",
            "Asset Class Examples.pdf",
        ],
        "notes": [
            "Order a benefits analysis; if moving from straight-line to accelerated, file Form 3115.",
            "Engineered study recommended; maintain invoices, drawings, closing statements."
        ]
    },
    {
        "name": "Family Management Company (Paying Children Reasonably)",
        "summary": "Establish LLC + EIN; pay reasonable wages for real work; document hours/tasks; ensure payroll/W-2 where required.",
        "irs_links": [
            {"label": "IRS Publication 15 (Circular E) – Employer’s Tax Guide", "url": "https://www.irs.gov/publications/p15"},
            {"label": "IRS – Family Help (children employed by parents)", "url": "https://www.irs.gov/businesses/small-businesses-self-employed/family-help"},
        ],
        "downloads": [
            "Family Management Company-White Paper.pdf",
            "Family Management Company-App.pdf",
        ],
        "notes": [
            "Wage must be reasonable, age-appropriate, and for bona fide services.",
            "Entity type affects FICA/FUTA rules; maintain clean invoicing and payroll records."
        ]
    },
    {
        "name": "Oil & Gas Investment (IDCs & Depletion)",
        "summary": "Potential current-year deduction for intangible drilling costs (IDCs) and ongoing percentage depletion (where eligible).",
        "irs_links": [
            {"label": "26 U.S. Code § 263(c) – Intangible drilling and development costs", "url": "https://www.law.cornell.edu/uscode/text/26/263"},
            {"label": "26 U.S. Code § 611–613 – Depletion", "url": "https://www.law.cornell.edu/uscode/text/26/611"},
            {"label": "IRS Publication 535 – Business Expenses", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Oil and Gas Investment - White Paper.pdf",
            "Oil and Gas Investment - App.pdf",
        ],
        "notes": [
            "Suitability review required; track IDC vs tangible allocation; expect K-1 reporting.",
            "Returns vary; investment risk disclosure is essential."
        ]
    },

    # ---- Add more house strategies here as you build them out ----
    # {
    #     "name": "Accountable Plan",
    #     "summary": "Reimburse employees/owners for business expenses, non-taxable when substantiated.",
    #     "irs_links": [{"label": "IRS Publication 463 – Travel, Gift, Car", "url": "https://www.irs.gov/publications/p463"}],
    #     "downloads": [],
    #     "notes": ["Written plan + receipts required.", "Reimbursements reduce taxable wages."]
    # },
]

def file_exists(fname: str) -> bool:
    return Path(fname).exists()

def render_strategy(block: dict):
    st.subheader(block["name"])
    st.write(block["summary"])

    if block.get("irs_links"):
        st.markdown("**Authoritative References**")
        for ref in block["irs_links"]:
            st.markdown(f"- [{ref['label']}]({ref['url']})")

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
                st.markdown(f"- _{fname} (file not found in repo)_")

    if block.get("notes"):
        st.markdown("**Implementation Notes**")
        for n in block["notes"]:
            st.markdown(f"- {n}")

    st.divider()

for entry in STRATEGIES:
    render_strategy(entry)

st.caption("Amatore & Co © 2025 — These materials are for planning/education; confirm positions before filing.")
