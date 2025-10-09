import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Amatore & Co — Tax Strategies", page_icon="📘", layout="centered")

LOGO_PATH = Path("amatore_collc_cover.jpg")
if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), use_container_width=True)

st.title("📘 Amatore & Co — Tax Strategies")
st.caption("Authoritative references + your client handouts, all in one place.")

# Helper: check file exists in repo root
def file_exists(fname: str) -> bool:
    return Path(fname).exists()

def downloads_section(files):
    if not files:
        return
    st.markdown("**Client Handouts**")
    for fname in files:
        if file_exists(fname):
            with open(fname, "rb") as f:
                st.download_button(label=f"Download: {fname}", data=f.read(), file_name=fname)
        else:
            st.markdown(f"- _{fname} (file not found in repo)_")

def refs_section(refs):
    if not refs:
        return
    st.markdown("**IRS References**")
    for r in refs:
        st.markdown(f"- [{r['label']}]({r['url']})")

def notes_section(notes):
    if not notes:
        return
    st.markdown("**Implementation Notes**")
    for n in notes:
        st.markdown(f"- {n}")

# ----------------------------------------------------------------
# Strategy Catalog (synchronized with the calculator v6.3)
# ----------------------------------------------------------------
STRATEGIES = [
    {
        "name": "Augusta Rule (IRC §280A(g))",
        "summary": "Rent your personal residence to your business up to 14 days/year — income excluded; business deducts FMV rent.",
        "irs": [
            {"label": "26 U.S. Code § 280A(g) – Dwelling unit used as a residence", "url": "https://www.law.cornell.edu/uscode/text/26/280A"},
            {"label": "IRS Publication 535 – Business Expenses", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Augusta Rule - Implementation.pdf",
            "Lease Agreement.pdf",
        ],
        "notes": [
            "Document business purpose (agenda/minutes) and FMV (3+ comps).",
            "Do not exceed 14 days; do not issue a 1099 to yourself."
        ]
    },
    {
        "name": "Cost Segregation (MACRS/Bonus/§179)",
        "summary": "Reclassify building components into shorter lives to accelerate depreciation; often paired with bonus and/or §179.",
        "irs": [
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
            "Order a benefits analysis to confirm savings.",
            "Engineer study recommended; maintain closing/build docs; file 3115 if required."
        ]
    },
    {
        "name": "Oil & Gas Investment (IDCs & Depletion)",
        "summary": "Potential current-year deduction for intangible drilling costs (IDCs) and ongoing percentage depletion where eligible.",
        "irs": [
            {"label": "26 U.S. Code § 263(c) – Intangible drilling and development costs", "url": "https://www.law.cornell.edu/uscode/text/26/263"},
            {"label": "26 U.S. Code §§ 611–613 – Depletion", "url": "https://www.law.cornell.edu/uscode/text/26/611"},
            {"label": "IRS Publication 535 – Business Expenses", "url": "https://www.irs.gov/publications/p535"},
        ],
        "downloads": [
            "Oil and Gas Investment - White Paper.pdf",
            "Oil and Gas Investment - App.pdf",
        ],
        "notes": [
            "Perform suitability review; understand risks and IDC vs. tangible allocation.",
            "Expect K-1 reporting; track depletion."
        ]
    },
    {
        "name": "Family Management Company (Hiring Your Kids)",
        "summary": "Compensate children for bona fide services via a family LLC; wages must be reasonable and documented.",
        "irs": [
            {"label": "IRS — Family Help (children employed by parents)", "url": "https://www.irs.gov/businesses/small-businesses-self-employed/family-help"},
            {"label": "IRS Publication 15 (Circular E) – Employer’s Tax Guide", "url": "https://www.irs.gov/publications/p15"},
        ],
        "downloads": [
            "Family Management Company-White Paper.pdf",
            "Family Management Company-App.pdf",
        ],
        "notes": [
            "Form LLC + EIN, open dedicated bank account.",
            "Track hours & tasks; run payroll/W-2 when required; maintain invoices."
        ]
    },
    {
        "name": "Equipment Leasing",
        "summary": "Lease payments for business-use equipment are deductible.",
        "irs": [{"label": "IRS Publication 535 – Business Expenses", "url": "https://www.irs.gov/publications/p535"}],
        "downloads": [],
        "notes": ["Maintain lease documents and business-use percentage.", "Keep payment evidence."]
    },
    {
        "name": "Accelerated Depreciation",
        "summary": "Bonus/§179/MACRS for qualifying property used in business.",
        "irs": [
            {"label": "26 U.S. Code § 179", "url": "https://www.law.cornell.edu/uscode/text/26/179"},
            {"label": "26 U.S. Code § 168 (MACRS)", "url": "https://www.law.cornell.edu/uscode/text/26/168"},
        ],
        "downloads": [],
        "notes": ["Confirm eligibility & basis; coordinate with any cost segregation."]
    },
    {
        "name": "Accountable Plan",
        "summary": "Reimburse owners/employees for substantiated expenses; non-taxable to recipient, deductible to business.",
        "irs": [{"label": "IRS Publication 463 – Travel, Gift, Car", "url": "https://www.irs.gov/publications/p463"}],
        "downloads": [],
        "notes": ["Adopt a written plan; collect timely receipts; reimburse through payroll/AP."]
    },
    {
        "name": "Business Travel Expenses",
        "summary": "Ordinary & necessary travel costs for business are deductible.",
        "irs": [{"label": "IRS Publication 463 – Travel, Gift, Car", "url": "https://www.irs.gov/publications/p463"}],
        "downloads": [],
        "notes": ["Keep agendas/receipts; document business purpose."]
    },
    {
        "name": "Board of Directors Fees",
        "summary": "Fees paid to independent directors for services are deductible.",
        "irs": [{"label": "IRS Publication 535 – Business Expenses", "url": "https://www.irs.gov/publications/p535"}],
        "downloads": [],
        "notes": ["Maintain agreements/minutes; issue 1099-NEC where applicable."]
    },
    {
        "name": "Defined Benefit Plan",
        "summary": "Employer contributions are deductible; high potential deferrals, but require actuarial/TPA oversight.",
        "irs": [{"label": "IRS Publication 560 – Retirement Plans for Small Business", "url": "https://www.irs.gov/publications/p560"}],
        "downloads": [],
        "notes": ["Coordinate with actuary/TPA; fund by deadlines; keep plan documents."]
    },
    {
        "name": "Educational Assistance Program (IRC §127)",
        "summary": "Up to $5,250 per employee excludable; employer deduction allowed.",
        "irs": [{"label": "26 U.S. Code § 127 – Educational assistance programs", "url": "https://www.law.cornell.edu/uscode/text/26/127"}],
        "downloads": [],
        "notes": ["Adopt written plan; track eligible expenses and recipients."]
    },
    {
        "name": "Home Office Deduction",
        "summary": "Exclusive & regular use for business; simplified or actual-expense method.",
        "irs": [{"label": "IRS Publication 587 – Business Use of Your Home", "url": "https://www.irs.gov/publications/p587"}],
        "downloads": [],
        "notes": ["Document square footage and exclusive use; retain expense records."]
    },
    {
        "name": "SIMPLE IRA (Employer Contributions)",
        "summary": "Employer contributions to SIMPLE are deductible to the business.",
        "irs": [{"label": "IRS Publication 560 – Retirement Plans for Small Business", "url": "https://www.irs.gov/publications/p560"}],
        "downloads": [],
        "notes": ["Adopt plan; deposit contributions timely; observe limits."]
    },
    {
        "name": "Employer Retirement Match",
        "summary": "Employer match contributions (401(k)/SIMPLE/etc.) are deductible.",
        "irs": [{"label": "IRS Publication 560 – Retirement Plans for Small Business", "url": "https://www.irs.gov/publications/p560"}],
        "downloads": [],
        "notes": ["Coordinate plan document and funding deadlines; track eligibility."]
    },
    {
        "name": "Maximize Retirement Contributions",
        "summary": "Maximize employer-side contributions (e.g., SEP, Solo 401(k)) to reduce business income.",
        "irs": [{"label": "IRS Publication 560 – Retirement Plans for Small Business", "url": "https://www.irs.gov/publications/p560"}],
        "downloads": [],
        "notes": ["Confirm contribution limits with TPA/CPA; coordinate with W-2 comp."]
    },
    {
        "name": "Donor Advised Fund (DAF)",
        "summary": "Charitable donation to DAF; timing control with AGI limits and carryforwards.",
        "irs": [{"label": "IRS Publication 526 – Charitable Contributions", "url": "https://www.irs.gov/publications/p526"}],
        "downloads": [],
        "notes": ["Obtain written acknowledgements; track AGI limits and carryforwards."]
    },
    {
        "name": "Installment Sale",
        "summary": "Defer recognition of gain to cash received; current-year capital gain can be lower.",
        "irs": [{"label": "IRS Publication 537 – Installment Sales", "url": "https://www.irs.gov/publications/p537"}],
        "downloads": [],
        "notes": ["Structure properly; compute gross profit %, basis, and interest component."]
    },
    {
        "name": "Roth IRA Conversion",
        "summary": "Converting pre-tax IRA to Roth adds ordinary income now; future qualified growth tax-free.",
        "irs": [{"label": "IRS Publication 590-A – Contributions to IRAs", "url": "https://www.irs.gov/publications/p590a"}],
        "downloads": [],
        "notes": ["Model bracket fill-up; consider IRMAA/phaseout implications."]
    },
]

# Render
for s in STRATEGIES:
    with st.container(border=True):
        st.subheader(s["name"])
        st.write(s["summary"])
        refs_section(s.get("irs", []))
        downloads_section(s.get("downloads", []))
        notes_section(s.get("notes", []))
st.caption("Amatore & Co © 2025 — Planning & education only; confirm positions before filing.")
