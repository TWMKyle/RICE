import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

# --- 1. CONFIGURATION & PAGE INITIALIZATION ---
st.set_page_config(
    page_title="Rice Enterprise Core", 
    page_icon="🌾", 
    layout="wide"
)

# 💡 Shared Cloud Spreadsheet Link (Remember to replace this with your real link!)
RICE_SHEET_URL = "https://google.com"

# Persistent Memory Initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# --- 2. DYNAMIC REGISTRY PIPELINE LOAD ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    users_df = conn.read(spreadsheet=RICE_SHEET_URL, worksheet="Users", ttl=0)
    
    # 💡 FIX: Clean and standardize the column headers themselves to get rid of hidden spaces/caps!
    users_df.columns = [str(col).strip().lower() for col in users_df.columns]
    
    # Verify the cleaned headers match what we expect
    for col in ["uz", "pc", "auth"]:
        if col in users_df.columns:
            users_df[col] = users_df[col].astype(str).str.strip()
        else:
            st.error(f"❌ Structural database error. Missing column `{col}` from your Users worksheet.")
            st.info(f"📋 What the code actually sees in your sheet row 1: {list(users_df.columns)}")
            st.stop()
        
    USER_CREDENTIALS = dict(zip(users_df["uz"].str.upper(), users_df["pc"]))
except Exception as e:
    st.error(f"❌ User registry failure. Ensure a worksheet tab named 'Users' exists with headers `uz`, `pc`, `auth`. Error: {e}")
    st.stop()

# --- 3. SCENARIO A: THE SECURE LOGIN GATE ---
if not st.session_state.logged_in:
    st.title("🌾 Rice Corporate Security Terminal")
    st.warning("🔒 This portal requires authentication to view, count, and manage production data rows.")
    
    with st.form("secure_rice_login_form"):
        username_input = st.text_input("Username").strip().upper()
        password_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Authenticate Profile")
        
        if submit_login:
            if username_input in USER_CREDENTIALS and USER_CREDENTIALS[username_input] == password_input:
                st.session_state.logged_in = True
                st.session_state.current_user = username_input
                st.success(f"Access granted for user: {username_input}")
                st.rerun()
            else:
                st.error("Authentication rejected. Invalid credentials combination.")

# --- 4. SCENARIO B: AUTHENTICATED ACCESS RUNSPACE ---
else:
    active_user = st.session_state.current_user
    user_row = users_df[users_df["uz"].str.upper() == active_user]
    raw_auth_value = str(user_row["auth"].iloc[0]).strip().upper() if not user_row.empty else "VIEWONLY"
    
    is_read_only = (raw_auth_value == "VIEWONLY")

    # Global Header & Navigation Sidebar
    st.title("🌾 Rice Inventory & Commercial Operations Hub")
    with st.sidebar:
        st.info(f"👤 **Active User:** {active_user}\n\n🏷️ **Auth Role:** {raw_auth_value}")
        if st.button("Log Out of Workspace"):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.rerun()

    # --- INITIALIZE MULTI-TAB ARCHITECTURE ---
    tab1, tab2, tab3 = st.tabs(["🛒 Sales Transactions", "📊 Sales Reports", "📋 Product Updates"])

    # Load Databases up front to use across tabs cleanly
    try:
        inventory_df = conn.read(spreadsheet=RICE_SHEET_URL, worksheet="Rice_Inventory", ttl=0)
        sales_df = conn.read(spreadsheet=RICE_SHEET_URL, worksheet="Sales_Transactions", ttl=0)
        
        # 💡 BUG PREVENTER: Clean currency text strings (strip out ₱, $, and commas) before type conversion
        for money_col in ["Cost_Price", "Retail_Price"]:
            if money_col in inventory_df.columns:
                inventory_df[money_col] = (
                    inventory_df[money_col]
                    .astype(str)
                    .str.replace("₱", "", regex=False)
                    .str.replace("$", "", regex=False)
                    .str.replace(",", "", regex=False)
                    .str.strip()
                )
        
        # 💡 BUG PREVENTER: Enforce strict, clean datatypes across ALL core layout columns
        inventory_df["SKU"] = inventory_df["SKU"].fillna("").astype(str).str.strip()
        inventory_df["Rice_Variety"] = inventory_df["Rice_Variety"].fillna("").astype(str).str.strip()
        inventory_df["Packaging"] = inventory_df["Packaging"].fillna("Bag").astype(str).str.strip()
        inventory_df["Last_Updated"] = inventory_df["Last_Updated"].fillna("").astype(str).str.strip()
        
        inventory_df["Bag_Weight_KG"] = pd.to_numeric(inventory_df["Bag_Weight_KG"], errors='coerce').fillna(0).astype(int)
        inventory_df["Stock_Count"] = pd.to_numeric(inventory_df["Stock_Count"], errors='coerce').fillna(0).astype(int)
        inventory_df["Cost_Price"] = pd.to_numeric(inventory_df["Cost_Price"], errors='coerce').fillna(0.0).astype(float)
        inventory_df["Retail_Price"] = pd.to_numeric(inventory_df["Retail_Price"], errors='coerce').fillna(0.0).astype(float)
        
        # Build clean dynamic selection list for dropdown configs
        baseline_options = {"Jasmine", "Sinandomeng", "Basmati", "Brown Rice", "Sticky Rice"}
        found_options = set(inventory_df["Rice_Variety"].unique())
        dropdown_choices = list(baseline_options.union(found_options))
        if "" in dropdown_choices: dropdown_choices.remove("")
        
    except Exception as e:
        st.error(f"❌ Database load failure. Verify spreadsheet tabs and column names. Details: {e}")
        st.stop()

    # ==========================================
    # TAB 1: SALES TRANSACTIONS (DEDUCTS STOCK)
    # ==========================================
    with tab1:
        st.subheader("🛒 Register New Point-of-Sale Transaction")
        
        if is_read_only:
            st.error("⚠️ Read-Only Restriction: Your account profile is blocked from filing new cash transactions.")
        else:
            if inventory_df.empty:
                st.info("No items available in inventory to sell.")
            else:
                with st.form("pos_sale_entry_form", clear_on_submit=True):
                    # Display Description combo string to avoid bag vs sack sizing confusion
                    inventory_df["Display_Label"] = inventory_df["Rice_Variety"] + " (" + inventory_df["SKU"] + ") [" + inventory_df["Packaging"] + "]"
                    product_selection = st.selectbox("Select Rice Item to Sell", options=inventory_df["Display_Label"].unique())
                    
                    # Extract the true targeted matching entry row parameters
                    selected_idx = inventory_df[inventory_df["Display_Label"] == product_selection].index[0]
                    selected_row = inventory_df.loc[selected_idx]
                    
                    current_stock = int(selected_row["Stock_Count"])
                    retail_price = float(selected_row["Retail_Price"])
                    target_sku = selected_row["SKU"]
                    target_variety = selected_row["Rice_Variety"]
                    target_packaging = selected_row["Packaging"]
                    
                    st.caption(f"💡 Current Live Stock Level: **{current_stock}** {target_packaging.lower()}(s) left | Unit Retail Price: **₱{retail_price:,.2f}**")
                    
                    qty_to_sell = st.number_input(f"Quantity of {target_packaging}s Sold", min_value=1, max_value=int(current_stock) if current_stock > 0 else 1, step=1)
                    
                    submit_sale = st.form_submit_button("Log Transaction", type="primary")
                    
                    if submit_sale:
                        if current_stock < qty_to_sell:
                            st.error("❌ Out of stock! Transaction blocked due to insufficient unit quantities.")
                        else:
                            # 1. Map properties array into new sales log line
                            new_sale_row = pd.DataFrame([{
                                "Transaction_ID": str(uuid.uuid4())[:8].upper(),
                                "Date_Time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "SKU": target_sku,
                                "Rice_Variety": target_variety,
                                "Packaging": target_packaging,
                                "Quantity_Bags": int(qty_to_sell),
                                "Price_Per_Bag": float(retail_price),
                                "Total_Amount": float(qty_to_sell * retail_price),
                                "Encoder": active_user
                            }])
                            
                            # 2. Subtract sold stock straight out of live manifest dataframe
                            inventory_df.loc[selected_idx, "Stock_Count"] = current_stock - qty_to_sell
                            inventory_df["Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            # Cleanup display formatting helpers before pushing up to server
                            inventory_df = inventory_df.drop(columns=["Display_Label"])
                            
                            # 3. Commit data updates back upstream concurrently
                            updated_sales_df = pd.concat([sales_df, new_sale_row], ignore_index=True)
                            
                            conn.update(spreadsheet=RICE_SHEET_URL, data=updated_sales_df, worksheet="Sales_Transactions")
                            conn.update(spreadsheet=RICE_SHEET_URL, data=inventory_df, worksheet="Rice_Inventory")
                            
                            st.success(f"🎉 Sale successfully logged! Subtracted **{qty_to_sell}** {target_packaging.lower()}(s) from {target_variety} inventory.")


    # ==========================================
    # TAB 2: SALES REPORTS (ANALYTICS SUMMARY)
    # ==========================================
    with tab2:
        st.subheader("📊 Commercial Sales Activity Logs")
        
        if not sales_df.empty:
            # Reassert clean metrics data constraints
            sales_df["Quantity_Bags"] = pd.to_numeric(sales_df["Quantity_Bags"], errors='coerce').fillna(0)
            sales_df["Total_Amount"] = pd.to_numeric(sales_df["Total_Amount"], errors='coerce').fillna(0.0)
            
            total_revenue_earned = sales_df["Total_Amount"].sum()
            total_units_moved = sales_df["Quantity_Bags"].sum()
            total_transactions_count = len(sales_df)
            
            rep1, rep2, rep3 = st.columns(3)
            with rep1:
                st.metric("Gross Sales Revenue", f"₱{total_revenue_earned:,.2f}")
            with rep2:
                st.metric("Total Items Sold (Bags/Sacks)", f"{int(total_units_moved):,} units")
            with rep3:
                st.metric("Transactions Settled", f"{total_transactions_count:,} records")
                
            st.divider()
            st.write("### Complete Sales Ledger Transaction History")
            st.dataframe(sales_df.sort_values(by="Date_Time", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("No recorded transactions found inside your spreadsheet history file yet.")

    # ==========================================
    # TAB 3: PRODUCT UPDATES (PREVIOUS PROJECT CODE)
    # ==========================================
    with tab3:
        st.subheader("📋 Master Stock Manifest Control")
        
        # Strip structural display label fields if present from Tab 1 operations
        if "Display_Label" in inventory_df.columns:
            inventory_df = inventory_df.drop(columns=["Display_Label"])

        # Dynamic metric indicators
        total_bags = int(inventory_df["Stock_Count"].sum())
        total_weight_tons = (inventory_df["Stock_Count"] * inventory_df["Bag_Weight_KG"]).sum() / 1000
        total_asset_value = (inventory_df["Stock_Count"] * inventory_df["Cost_Price"]).sum()
        potential_revenue = (inventory_df["Stock_Count"] * inventory_df["Retail_Price"]).sum()

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Stock Count (All Units)", f"{total_bags:,} units")
        with m2:
            st.metric("Total Weight Volume", f"{total_weight_tons:,.2f} Tons")
        with m3:
            st.metric("Inventory Asset Cost", f"₱{total_asset_value:,.2f}")
        with m4:
            st.metric("Estimated Retail Value", f"₱{potential_revenue:,.2f}")

        st.divider()

        left_pane, right_pane = st.columns([3, 1])
        with left_pane:
            st.markdown('<span style="color: white; font-size: 0.85rem;">✏️ Modify inventory cells below. Changes must be explicitly saved to overwrite the ledger.</span>', unsafe_allow_html=True)
            
            # Setup list tracking array strings for role isolation verification
            required_cols = ["SKU", "Rice_Variety", "Packaging", "Bag_Weight_KG", "Stock_Count", "Cost_Price", "Retail_Price", "Last_Updated"]
            disabled_columns = ["Last_Updated"]
            if is_read_only:
                st.error("⚠️ Read-Only Profile: Grid modifications are locked out.")
                disabled_columns = required_cols

            edited_df = st.data_editor(
                inventory_df, 
                num_rows="viewer" if is_read_only else "dynamic", 
                use_container_width=True,
                column_config={
                    "SKU": st.column_config.TextColumn("SKU Code", required=True, disabled=("SKU" in disabled_columns)),
                    "Rice_Variety": st.column_config.SelectboxColumn("Rice Variety", options=dropdown_choices, required=True, disabled=("Rice_Variety" in disabled_columns)),
                    "Packaging": st.column_config.SelectboxColumn("Packaging", options=["Bag", "Sack"], required=True, disabled=("Packaging" in disabled_columns)),
                    "Bag_Weight_KG": st.column_config.NumberColumn("Weight (KG)", min_value=1, format="%d kg", disabled=("Bag_Weight_KG" in disabled_columns)),
                    "Stock_Count": st.column_config.NumberColumn("Stock Quantity", min_value=0, format="%d", disabled=("Stock_Count" in disabled_columns)),
                    "Cost_Price": st.column_config.NumberColumn("Cost per Unit", min_value=0.0, format="₱%.2f", disabled=("Cost_Price" in disabled_columns)),
                    "Retail_Price": st.column_config.NumberColumn("Retail per Unit", min_value=0.0, format="₱%.2f", disabled=("Retail_Price" in disabled_columns)),
                    "Last_Updated": st.column_config.TextColumn("Last Modified", disabled=True)
                }
            )
            
            if not is_read_only:
                if st.button("Save & Sync Stock Changes", type="primary"):
                    with st.spinner("Writing transactions securely to cloud registry..."):
                        # Reassert string datatypes on edited matrix data lines
                        edited_df["SKU"] = edited_df["SKU"].fillna("").astype(str).str.strip()
                        edited_df["Rice_Variety"] = edited_df["Rice_Variety"].fillna("Jasmine").astype(str).str.strip()
                        edited_df["Packaging"] = edited_df["Packaging"].fillna("Bag").astype(str).str.strip()
                        edited_df["Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        conn.update(spreadsheet=RICE_SHEET_URL, data=edited_df, worksheet="Rice_Inventory")
                        st.success("🎉 Inventory dashboard synchronized perfectly with cloud storage!")
                        st.rerun()

        with right_pane:
            st.subheader("⚠️ Alerts")
            low_stock_threshold = 10
            low_stock_df = inventory_df[inventory_df["Stock_Count"] <= low_stock_threshold]
            
            if not low_stock_df.empty:
                for _, row in low_stock_df.iterrows():
                    st.error(f"**{row['Rice_Variety']} ({row['SKU']})**\n\nOnly **{int(row['Stock_Count'])}** {row['Packaging'].lower()}(s) remaining!")
            else:
                st.success("✅ Stock parameters clear.")
