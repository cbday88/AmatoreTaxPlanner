import streamlit as st

st.set_page_config(page_title="Amatore & Co Tax Strategies", page_icon="💼")

# --- Header ---
st.image("amatore_collc_cover.jpg", width="stretch")
st.title("💼 Amatore & Co — Tax Strategies")
st.caption("Helping clients reduce taxes through strategic planning")

# --- Strategy Selector ---
strategy = st.selectbox(
    "Select a Strategy",
    [
        "Oil & Gas Investment",
        "Augusta Rule",
        "Family Management Company",
        "Cost Segregation"
    ]
)

# --- Oil & Gas Investment ---
if strategy == "Oil & Gas Investment":
    st.header("Oil & Gas Investment")
    st.write("""
An investment in oil and gas can reduce a taxpayer’s liability through **Intangible Drilling Costs (IDCs)**,
which are often largely deductible in year one. Tangible Drilling Costs (TDCs) are capitalized and depreciated over time.
Investors may also qualify for a **depletion allowance**, providing continued deductions over the life of the well.
    """)
    st.subheader("Possible Risk")
    st.write("• Returns vary just like any investment.\n• Market conditions may impact results.")
    st.subheader("Implementation Steps")
    st.write("""
1️⃣ Determine Investment (Client) — Review offering, confirm risk tolerance, and objectives.  
2️⃣ Identify Deductible Drilling Costs (Advisor) — Separate IDC vs TDC.  
3️⃣ Apply Depletion Allowance (Advisor).  
4️⃣ Leverage Accelerated Depreciation (Advisor).
    """)
    with open("Oil and Gas Investment - White Paper.pdf", "rb") as f:
        st.download_button("📄 Download White Paper", f, file_name="Oil_and_Gas_White_Paper.pdf")
    with open("Oil and Gas Investment - App.pdf", "rb") as f:
        st.download_button("📄 Download Application", f, file_name="Oil_and_Gas_App.pdf")

# --- Augusta Rule ---
elif strategy == "Augusta Rule":
    st.header("Augusta Rule")
    st.write("""
Homeowners can rent their personal residence for up to **14 days per year** without reporting the income.
The business deducts the rent as an expense, and the homeowner receives it **tax-free**.
    """)
    st.subheader("Possible Risk")
    st.write("""
• Failure to document meetings or agreements correctly.  
• Overstating fair rental value.  
• Renting more than 14 days removes the exemption.
    """)
    st.subheader("Implementation Steps")
    st.write("""
1️⃣ Confirm Eligibility — Home must be primary or secondary.  
2️⃣ Determine Market Rate — Document comparable rentals.  
3️⃣ Sign Lease Agreement — Outline purpose, rate, and duration.  
4️⃣ Keep Documentation — Rental agreement, check, and meeting minutes.
    """)
    with open("Augusta Rule - Implementation.pdf", "rb") as f:
        st.download_button("📄 Download Implementation Guide", f, file_name="Augusta_Rule_Implementation.pdf")
    with open("Lease Agreement.pdf", "rb") as f:
        st.download_button("📄 Download Lease Agreement", f, file_name="Augusta_Rule_Lease.pdf")

# --- Family Management Company ---
elif strategy == "Family Management Company":
    st.header("Family Management Company")
    st.write("""
A **Family Management Company (FMC)** allows owners to employ family members—especially children—for legitimate work,
shifting income into lower tax brackets and teaching business skills.
    """)
    st.subheader("Possible Risk")
    st.write("• Wages must be reasonable and documented.\n• FICA taxes apply if under an S-Corp.")
    st.subheader("Implementation Steps")
    st.write("""
1️⃣ Entity Formation — Form an LLC and obtain an EIN.  
2️⃣ Bank Account Setup — Separate from personal accounts.  
3️⃣ Invoicing Process — Document hours and tasks.  
4️⃣ Payment & Payroll — Issue W-2s as required.
    """)
    with open("Family Management Company-White Paper.pdf", "rb") as f:
        st.download_button("📄 Download White Paper", f, file_name="Family_Management_White_Paper.pdf")
    with open("Family Management Company-App.pdf", "rb") as f:
        st.download_button("📄 Download Application", f, file_name="Family_Management_App.pdf")

# --- Cost Segregation ---
elif strategy == "Cost Segregation":
    st.header("Cost Segregation")
    st.write("""
A **Cost Segregation Study** accelerates depreciation by reclassifying building components
into shorter recovery periods—improving cash flow and reducing taxable income.
    """)
    st.subheader("Possible Risk")
    st.write("• Misclassification or incomplete study may cause IRS adjustments.")
    st.subheader("Implementation Steps")
    st.write("""
1️⃣ Conduct Benefits Analysis — Determine eligibility and savings.  
2️⃣ Client Agreement — Sign the study agreement.  
3️⃣ Property Data Collection — Gather closing statements, invoices, drawings.  
4️⃣ On-Site Review — Engineers classify components (5-, 7-, 15-year).  
5️⃣ File Form 3115 to document method change.
    """)
    with open("Cost Segregation-App.pdf", "rb") as f:
        st.download_button("📄 Download Cost Segregation App", f, file_name="Cost_Segregation_App.pdf")
    with open("Asset Class Examples.pdf", "rb") as f:
        st.download_button("📄 Download Asset Class Examples", f, file_name="Cost_Segregation_Assets.pdf")

st.write("---")
st.caption("© 2025 Amatore & Co LLC | Educational use only — confirm all tax positions with your advisor.")
