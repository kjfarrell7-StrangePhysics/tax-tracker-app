import sqlite3
import streamlit as st
import pandas as pd
from datetime import date

# -----------------------------------------------------------------------------
# DATABASE INITIALIZATION
# -----------------------------------------------------------------------------
DB_FILE = "tax_tracker.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Tax Years
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tax_years (
            tax_year INTEGER PRIMARY KEY
        );
        """)
        
        # 2. Income Categories
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS income_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            requires_withholding_check BOOLEAN,
            irs_form_mapping TEXT
        );
        """)
        
        # 3. Expense Categories
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            irs_tax_form TEXT NOT NULL,
            tax_benefit_type TEXT NOT NULL
        );
        """)

        # 4. Income Transactions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS income_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tax_year INTEGER NOT NULL,
            entry_date DATE NOT NULL,
            payer_name TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            gross_amount DECIMAL(10,2) NOT NULL,
            fed_tax_withheld DECIMAL(10,2) DEFAULT 0.00,
            state_tax_withheld DECIMAL(10,2) DEFAULT 0.00,
            notes TEXT,
            FOREIGN KEY (category_id) REFERENCES income_categories(id)
        );
        """)

        # 5. Expense Transactions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tax_year INTEGER NOT NULL,
            entry_date DATE NOT NULL,
            vendor_or_payee TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            gross_amount DECIMAL(10,2) NOT NULL,
            notes TEXT,
            FOREIGN KEY (category_id) REFERENCES expense_categories(id)
        );
        """)

        # Seed initial categories
        cursor.executemany("""
        INSERT OR IGNORE INTO income_categories (category_name, requires_withholding_check, irs_form_mapping)
        VALUES (?, ?, ?);
        """, [
            ('W-2 Salary & Teaching Stipends', 0, 'Form 1040 Line 1a'),
            ('University Research Grant / Fellowship', 1, 'Schedule 1 Line 8r'),
            ('Savings Interest', 1, 'Form 1040 Line 2b')
        ])

        cursor.executemany("""
        INSERT OR IGNORE INTO expense_categories (category_name, irs_tax_form, tax_benefit_type)
        VALUES (?, ?, ?);
        """, [
            ('Higher Education Tuition & Fees', 'Form 8863', 'Education Credit'),
            ('Adaptive Equipment & Medical Expenses', 'Schedule A (Line 1)', 'Itemized Deduction'),
            ('Traditional IRA Contribution', 'Schedule 1 (Line 20)', 'Above-the-Line Deduction'),
            ('Real Estate Property Taxes', 'Schedule A / IL 1040', 'Itemized & State Credit')
        ])

        cursor.execute("INSERT OR IGNORE INTO tax_years (tax_year) VALUES (2025), (2026);")
        conn.commit()

init_db()

# -----------------------------------------------------------------------------
# STREAMLIT UI SETUP
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Personal Tax & Expense Tracker", layout="wide")
st.title("📊 Personal Tax & Expense Tracker")

# Year Selector Sidebar
selected_year = st.sidebar.selectbox("Select Tax Year", [2026, 2025])

tab1, tab2, tab3 = st.tabs(["💰 Income Log", "💳 Deductions & Expenses", "📈 Annual Tax Summary"])

# -----------------------------------------------------------------------------
# TAB 1: INCOME LOG
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Log Income / Grant / Stipend")
    
    with get_connection() as conn:
        categories_df = pd.read_sql("SELECT id, category_name FROM income_categories", conn)
    
    cat_dict = dict(zip(categories_df['category_name'], categories_df['id']))

    with st.form("income_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        entry_date = col1.date_input("Date", date.today())
        payer_name = col2.text_input("Payer Name (e.g., School District, UChicago)")
        category_name = col3.selectbox("Income Category", list(cat_dict.keys()))

        col4, col5, col6 = st.columns(3)
        gross_amount = col4.number_input("Gross Amount ($)", min_value=0.0, step=50.0)
        fed_withheld = col5.number_input("Federal Tax Withheld ($)", min_value=0.0, step=10.0)
        state_withheld = col6.number_input("State Tax Withheld ($)", min_value=0.0, step=10.0)
        
        notes = st.text_input("Notes")
        submit_income = st.form_submit_button("Save Income Entry")

        if submit_income and payer_name and gross_amount > 0:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO income_transactions (tax_year, entry_date, payer_name, category_id, gross_amount, fed_tax_withheld, state_tax_withheld, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (selected_year, entry_date, payer_name, cat_dict[category_name], gross_amount, fed_withheld, state_withheld, notes))
                conn.commit()
            st.success("Income logged successfully!")

    st.markdown("---")
    st.write(f"### {selected_year} Logged Income")
    with get_connection() as conn:
        income_df = pd.read_sql(f"""
        SELECT i.entry_date AS Date, i.payer_name AS Payer, c.category_name AS Category, 
               i.gross_amount AS Gross, i.fed_tax_withheld AS Fed_Withheld, 
               i.state_tax_withheld AS State_Withheld, i.notes AS Notes
        FROM income_transactions i
        JOIN income_categories c ON i.category_id = c.id
        WHERE i.tax_year = {selected_year}
        ORDER BY i.entry_date DESC
        """, conn)
    st.dataframe(income_df, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 2: DEDUCTIONS & EXPENSES LOG
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Log Deductible Expense")

    with get_connection() as conn:
        exp_categories_df = pd.read_sql("SELECT id, category_name FROM expense_categories", conn)
    
    exp_cat_dict = dict(zip(exp_categories_df['category_name'], exp_categories_df['id']))

    with st.form("expense_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        exp_date = col1.date_input("Date", date.today())
        vendor = col2.text_input("Vendor / Payee (e.g., Bursar, Doctor)")
        exp_category = col3.selectbox("Deduction Category", list(exp_cat_dict.keys()))

        exp_amount = st.number_input("Total Expense Amount ($)", min_value=0.0, step=25.0)
        exp_notes = st.text_input("Notes")
        submit_exp = st.form_submit_button("Save Expense Entry")

        if submit_exp and vendor and exp_amount > 0:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO expense_transactions (tax_year, entry_date, vendor_or_payee, category_id, gross_amount, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (selected_year, exp_date, vendor, exp_cat_dict[exp_category], exp_amount, exp_notes))
                conn.commit()
            st.success("Expense logged successfully!")

    st.markdown("---")
    st.write(f"### {selected_year} Logged Deductions")
    with get_connection() as conn:
        expense_df = pd.read_sql(f"""
        SELECT e.entry_date AS Date, e.vendor_or_payee AS Vendor, c.category_name AS Category, 
               c.irs_tax_form AS Form_Destination, e.gross_amount AS Amount, e.notes AS Notes
        FROM expense_transactions e
        JOIN expense_categories c ON e.category_id = c.id
        WHERE e.tax_year = {selected_year}
        ORDER BY e.entry_date DESC
        """, conn)
    st.dataframe(expense_df, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 3: ANNUAL TAX SUMMARY (FOR FREE FILING APP)
# -----------------------------------------------------------------------------
with tab3:
    st.subheader(f"📊 {selected_year} Tax Return Ready Summary")
    st.caption("Use these pre-calculated totals when filling out FreeTaxUSA or Cash App Taxes.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Income & Withholdings")
        with get_connection() as conn:
            inc_summary = pd.read_sql(f"""
            SELECT c.category_name AS Category, 
                   c.irs_form_mapping AS Form_Line,
                   SUM(i.gross_amount) AS Total_Gross,
                   SUM(i.fed_tax_withheld) AS Total_Fed_Withheld,
                   SUM(i.state_tax_withheld) AS Total_State_Withheld,
                   CASE WHEN c.requires_withholding_check = 1 
                        THEN ROUND(SUM(i.gross_amount) * 0.20, 2) 
                        ELSE 0.00 END AS Estimated_Tax_Reserve
            FROM income_transactions i
            JOIN income_categories c ON i.category_id = c.id
            WHERE i.tax_year = {selected_year}
            GROUP BY c.id
            """, conn)
        st.dataframe(inc_summary, use_container_width=True)

    with col2:
        st.markdown("#### Deductions & Credits")
        with get_connection() as conn:
            ded_summary = pd.read_sql(f"""
            SELECT c.category_name AS Category, 
                   c.tax_benefit_type AS Type,
                   c.irs_tax_form AS Form_Line,
                   SUM(e.gross_amount) AS Total_Amount
            FROM expense_transactions e
            JOIN expense_categories c ON e.category_id = c.id
            WHERE e.tax_year = {selected_year}
            GROUP BY c.id
            """, conn)
        st.dataframe(ded_summary, use_container_width=True)
