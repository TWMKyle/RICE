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
RICE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1pY_t90mBbeZ6ujZnw-fO9MhnM0f8QfqURDYEUDr1y4Q/edit?gid=0#gid=0"


# Persistent Memory Initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# --- 2. DYNAMIC REGISTRY PIPELINE LOAD ---
# 💡 FIX: Pre-define the dictionary as empty so it always exists in memory
USER_CREDENTIALS = {}

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Read the specialized user credential sheet (ttl=0 ensures live permission changes sync instantly)
    users_df = conn.read(worksheet="Users", ttl=0)
    
    # Standardize security column arrays (strip trailing/leading whitespace blocks)
    for col in ["uz", "pc", "auth"]:
        if col in users_df.columns:
            users_df[col] = users_df[col].astype(str).str.strip()
        else:
            st.error(f"❌ Target column `{col}` was missing from your Users worksheet header row. Detected fields: {list(users_df.columns)}")
            st.stop()
    
    # Build live credentials bank mapping dictionary (Username: Passcode)
    USER_CREDENTIALS = dict(zip(users_df["uz"].str.upper(), users_df["pc"]))
    
except Exception as registry_error:
    st.error(f"❌ User database pipeline offline. Ensure your Google Sheet has a 'Users' tab with headers: uz, pc, auth. Details: {registry_error}")
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
        inventory_df["Stock_Count"] = pd.to_numeric(inventory_df["Stock_Count"], errors='coerce').fillna(0).astype(float)
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
    # TAB 1: SALES TRANSACTIONS (REPACKAGING WEIGHT LOGIC)
    # ==========================================
    with tab1:
        st.subheader("🛒 Register New Point-of-Sale Transaction")
        
        if is_read_only:
            st.error("⚠️ Read-Only Restriction: Your account profile is blocked from filing new transactions.")
        else:
            if inventory_df.empty:
                st.info("No items available in inventory to sell.")
            else:
                with st.form("pos_sale_entry_form", clear_on_submit=True):
                    # Combine labels but strictly target the WHOLESALE master item rows (e.g., 25kg Sacks)
                    inventory_df["Display_Label"] = inventory_df["Brand"] + " - " + inventory_df["Rice_Variety"] + " (" + inventory_df["SKU"] + ") [" + inventory_df["Packaging"] + "]"
                    product_selection = st.selectbox("Select Master Rice Inventory Item", options=inventory_df["Display_Label"].unique())
                    
                    # Extract the true targeted matching entry row parameters
                    selected_idx = inventory_df[inventory_df["Display_Label"] == product_selection].index
                    selected_row = inventory_df.loc[selected_idx].iloc[0]
                    
                    current_stock_sacks = float(selected_row["Stock_Count"])
                    sack_weight_kg = float(selected_row["Bag_Weight_KG"])
                    retail_price_per_bag = float(selected_row["Retail_Price"])  # Original base price
                    target_sku = selected_row["SKU"]
                    target_brand = selected_row["Brand"]
                    target_variety = selected_row["Rice_Variety"]
                    
                    # Calculate total available kilograms remaining in that specific wholesale stack
                    total_available_kg = current_stock_sacks * sack_weight_kg
                    
                    st.caption(f"💡 Current Live Stock Level: **{current_stock_sacks:,.2f}** Sacks remaining (Total available volume: **{total_available_kg:,.1f} kg**)")
                    st.divider()
                    
                    # 💡 REPACKAGING LAYOUT OPTION CONTROLS
                    col_unit, col_qty = st.columns(2)
                    with col_unit:
                        retail_size_kg = st.selectbox(
                            "Select Retail Package Size Sold", 
                            options=[2, 3], 
                            format_func=lambda x: f"{x} kg Small Bag"
                        )
                    with col_qty:
                        qty_repacked_bags_sold = st.number_input(
                            f"Quantity of {retail_size_kg}kg Bags Sold", 
                            min_value=1, 
                            step=1
                        )
                    
                    # 💡 MATHEMATICAL LOGIC: 
                    # 1. Compute total weight sold in kilograms
                    total_weight_sold_kg = float(retail_size_kg * qty_repacked_bags_sold)
                    
                    # 2. Convert total weight sold back into fractions of a wholesale sack
                    # Example: Selling five 3kg bags = 15kg. If master sack is 25kg, sacks_to_deduct = 15 / 25 = 0.60 sacks
                    sacks_to_deduct = total_weight_sold_kg / sack_weight_kg
                    
                    # 3. Dynamic Retail Pricing Rule: Base it proportionally on weight, or customize it
                    # Example: If a 25kg sack retails at ₱1,250, a 3kg bag automatically calculates as (3 / 25) * 1250 = ₱150
                    calculated_price_per_bag = (retail_size_kg / sack_weight_kg) * retail_price_per_bag
                    total_sale_amount = qty_repacked_bags_sold * calculated_price_per_bag
                    
                    st.info(f"💵 **Transaction Preview:** Total Weight Sold: `{total_weight_sold_kg} kg` | Price per bag: `₱{calculated_price_per_bag:,.2f}` | **Total Amount due: ₱{total_sale_amount:,.2f}**")
                    
                    submit_sale = st.form_submit_button("Log Transaction", type="primary")
                    
                    if submit_sale:
                        if total_available_kg < total_weight_sold_kg:
                            st.error(f"❌ Transaction Blocked! Insufficient volume. You are attempting to sell {total_weight_sold_kg}kg but only {total_available_kg}kg remains.")
                        else:
                            # 1. Map transaction data into your sales log sheet
                            new_sale_row = pd.DataFrame([{
                                "Transaction_ID": str(uuid.uuid4())[:8].upper(),
                                "Date_Time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "SKU": target_sku,
                                "Brand": target_brand,
                                "Rice_Variety": f"{target_variety} (Repacked {retail_size_kg}kg)",
                                "Packaging": "Small Bag",
                                "Quantity_Bags": int(qty_repacked_bags_sold),
                                "Price_Per_Bag": float(calculated_price_per_bag),
                                "Total_Amount": float(total_sale_amount),
                                "Encoder": active_user
                            }])
                            
                            # 2. SURGICAL DEDUCTION: Subtract the precise decimal fraction of the sack from your inventory dataframe
                            inventory_df.loc[selected_idx, "Stock_Count"] = current_stock_sacks - sacks_to_deduct
                            inventory_df["Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            # Cleanup layout helpers before pushing updates back online
                            inventory_df = inventory_df.drop(columns=["Display_Label"])
                            
                            # 3. Save updates concurrently across worksheets
                            updated_sales_df = pd.concat([sales_df, new_sale_row], ignore_index=True)
                            
                            conn.update(data=updated_sales_df, worksheet="Sales_Transactions")
                            conn.update(data=inventory_df, worksheet="Rice_Inventory")
                            
                            st.success(f"🎉 Success! Sold **{qty_repacked_bags_sold}** bags of {retail_size_kg}kg. Deducted **{sacks_to_deduct:.2f}** Sacks from the `{target_brand}` wholesale inventory.")
                            st.rerun()


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
    # TAB 3: PRODUCT UPDATES (WITH BRAND CONFIG)
    # ==========================================
    with tab3:
        st.subheader("📋 Master Stock Manifest Control")
        
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

        left_pane, right_pane = st.columns(2)
        with left_pane:
            st.markdown('<span style="color: white; font-size: 0.85rem;">✏Header text modifiers. Changes must be explicitly saved to overwrite the ledger.</span>', unsafe_allow_html=True)
            
            required_cols = ["Brand", "SKU", "Rice_Variety", "Packaging", "Bag_Weight_KG", "Stock_Count", "Cost_Price", "Retail_Price", "Last_Updated"]
            disabled_columns = ["Last_Updated"]
            if is_read_only:
                st.error("⚠️ Read-Only Profile: Grid modifications are locked out.")
                disabled_columns = required_cols

            edited_df = st.data_editor(
                inventory_df, 
                num_rows="viewer" if is_read_only else "dynamic", 
                use_container_width=True,
                column_config={
                    # 💡 NEW BRAND COLUMN DEFINED HERE:
                    "Brand": st.column_config.TextColumn("Product Brand", required=True, disabled=("Brand" in disabled_columns)),
                    "SKU": st.column_config.TextColumn("SKU Code", required=True, disabled=("SKU" in disabled_columns)),
                    "Rice_Variety": st.column_config.SelectboxColumn("Rice Variety", options=dropdown_choices, required=True, disabled=("Rice_Variety" in disabled_columns)),
                    "Packaging": st.column_config.SelectboxColumn("Packaging", options=["Bag", "Sack"], required=True, disabled=("Packaging" in disabled_columns)),
                    "Bag_Weight_KG": st.column_config.NumberColumn("Weight (KG)", min_value=1, format="%d kg", disabled=("Bag_Weight_KG" in disabled_columns)),
                    "Stock_Count": st.column_config.NumberColumn("Stock Quantity", min_value=0.0, format="%.2f", disabled=("Stock_Count" in disabled_columns)),
                    "Cost_Price": st.column_config.NumberColumn("Cost per Unit", min_value=0.0, format="₱%.2f", disabled=("Cost_Price" in disabled_columns)),
                    "Retail_Price": st.column_config.NumberColumn("Retail per Unit", min_value=0.0, format="₱%.2f", disabled=("Retail_Price" in disabled_columns)),
                    "Last_Updated": st.column_config.TextColumn("Last Modified", disabled=True)
                }
            )
            
            if not is_read_only:
                if st.button("Save & Sync Stock Changes", type="primary"):
                    with st.spinner("Writing transactions securely to cloud registry..."):
                        # Reassert string datatypes on edited matrix data lines
                        edited_df["Brand"] = edited_df["Brand"].fillna("Generic").astype(str).str.strip()
                        edited_df["SKU"] = edited_df["SKU"].fillna("").astype(str).str.strip()
                        edited_df["Rice_Variety"] = edited_df["Rice_Variety"].fillna("Jasmine").astype(str).str.strip()
                        edited_df["Packaging"] = edited_df["Packaging"].fillna("Bag").astype(str).str.strip()
                        edited_df["Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        conn.update(data=edited_df, worksheet="Rice_Inventory")
                        st.success("🎉 Inventory dashboard synchronized perfectly with cloud storage!")
                        st.rerun()

        with right_pane:
            st.subheader("⚠️ Alerts")
            
            # Use 'inventory_df' as it is the active data schema in this block
            low_stock_threshold = 10
            low_stock_df = inventory_df[inventory_df["Stock_Count"] <= low_stock_threshold]
            
            if not low_stock_df.empty:
                for _, row in low_stock_df.iterrows():
                    # Safely extract item configurations to present individual alerts
                    item_variety = str(row["Rice_Variety"])
                    item_sku = str(row["SKU"])
                    item_packaging = str(row["Packaging"]).lower()
                    item_qty = int(row["Stock_Count"])
                    
                    st.error(f"**{item_variety} ({item_sku})**\n\nOnly **{item_qty}** {item_packaging}(s) remaining!")
            else:
                st.success("✅ Stock parameters clear. All products sit safely above baseline thresholds.")

