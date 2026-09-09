import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- 1. INITIAL APP PAGE SETUP ---
st.set_page_config(
    page_title="Rice Inventory Engine", 
    page_icon="🌾", 
    layout="wide"
)

st.title("🌾 Rice Inventory & Price Control Hub")
st.markdown("Monitor stock levels, calculate total valuation, and override item constraints smoothly.")
st.divider()

# --- 2. CONNECT TO GOOGLE SHEETS PIPELINE ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # Fetch live spreadsheet matrix (ttl=0 avoids stale storage cache reads)
    master_df = conn.read(worksheet="Rice_Inventory", ttl=0)

    # Clean currency text strings (strip out ₱, $, and commas) before making numeric evaluations
    for money_col in ["Cost_Price", "Retail_Price"]:
        if money_col in master_df.columns:
            master_df[money_col] = (
                master_df[money_col]
                .astype(str)
                .str.replace("₱", "", regex=False)
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
    
    # 🌟 FIX 1: Explicitly normalize string text columns to remove hidden white-spaces and NaN blocks
    master_df["SKU"] = master_df["SKU"].fillna("").astype(str).str.strip()
    master_df["Rice_Variety"] = master_df["Rice_Variety"].fillna("Jasmine").astype(str).str.strip()
    master_df["Last_Updated"] = master_df["Last_Updated"].fillna("").astype(str).str.strip()
    
    # Standardize numeric data types cleanly to match data editor schemas
    master_df["Bag_Weight_KG"] = pd.to_numeric(master_df["Bag_Weight_KG"], errors='coerce').fillna(0).astype(int)
    master_df["Stock_Count"] = pd.to_numeric(master_df["Stock_Count"], errors='coerce').fillna(0).astype(int)
    master_df["Cost_Price"] = pd.to_numeric(master_df["Cost_Price"], errors='coerce').fillna(0.0).astype(float)
    master_df["Retail_Price"] = pd.to_numeric(master_df["Retail_Price"], errors='coerce').fillna(0.0).astype(float)

    # 🌟 FIX 2: Dynamically pull unique choices directly from your Google Sheet cells
    # This prevents crashes from minor typos while keeping your target options available
    baseline_options = {"Jasmine", "Sinandomeng", "Basmati", "Brown Rice", "Sticky Rice"}
    found_options = set(master_df["Rice_Variety"].unique())
    dropdown_choices = list(baseline_options.union(found_options))

except Exception as e:
    st.error(f"❌ Google Sheets Connection failed. Ensure the 'Rice_Inventory' tab exists with the correct columns. Trace: {e}")
    st.stop()

# --- 3. HIGH-UTILITY EXECUTIVE METRICS ---
# Execute live inventory logic sums based on current spreadsheet snapshot
total_bags = int(master_df["Stock_Count"].sum())
total_weight_tons = (master_df["Stock_Count"] * master_df["Bag_Weight_KG"]).sum() / 1000
total_asset_value = (master_df["Stock_Count"] * master_df["Cost_Price"]).sum()
potential_revenue = (master_df["Stock_Count"] * master_df["Retail_Price"]).sum()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Bags in Stock", f"{total_bags:,} bags")
with col2:
    st.metric("Total Weight Volume", f"{total_weight_tons:,.2f} Tons")
with col3:
    st.metric("Inventory Asset Cost", f"₱{total_asset_value:,.2f}")
with col4:
    st.metric("Estimated Retail Value", f"₱{potential_revenue:,.2f}")

st.divider()

# --- 4. DATA MANAGEMENT & LIVE ENTRY TERMINAL ---
left_pane, right_pane = st.columns([3, 1])

with left_pane:
    st.subheader("📋 Master Stock Manifest")
    st.markdown('<span style="color: white; font-size: 0.85rem;">✏️ Directly edit cells below to adjust stock counts or alter prices. New rows will auto-timestamp.</span>', unsafe_allow_html=True)
    
    # Render interactive spreadsheet grid
    edited_df = st.data_editor(
        master_df, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "SKU": st.column_config.TextColumn("SKU Code", required=True),
            # 🌟 FIX 3: Pass our combined, dynamic dropdown values array list here
            "Rice_Variety": st.column_config.SelectboxColumn("Rice Variety", options=dropdown_choices, required=True),
            "Bag_Weight_KG": st.column_config.NumberColumn("Weight (KG)", min_value=1, format="%d kg"),
            "Stock_Count": st.column_config.NumberColumn("Bags Count", min_value=0, format="%d"),
            "Cost_Price": st.column_config.NumberColumn("Cost per Bag", min_value=0.0, format="₱%.2f"),
            "Retail_Price": st.column_config.NumberColumn("Retail per Bag", min_value=0.0, format="₱%.2f"),
            "Last_Updated": st.column_config.TextColumn("Last Modified", disabled=True)
        }
    )
    
    # Save Action Control
    if st.button("Save & Sync Stock Changes", type="primary"):
        with st.spinner("Writing transactions securely to cloud registry..."):
            # Update modification timestamps for rows that changed
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            edited_df["Last_Updated"] = current_time
            
            # Commit the updated matrix upstream
            conn.update(data=edited_df, worksheet="Rice_Inventory")
            st.success("🎉 Inventory dashboard synchronized perfectly with cloud storage!")
            st.rerun()

with right_pane:
    st.subheader("⚠️ Low Stock Alerts")
    # Dynamically extract items below threshold buffer (e.g., fewer than 10 bags left)
    low_stock_threshold = 10
    low_stock_df = master_df[master_df["Stock_Count"] <= low_stock_threshold]
    
    if not low_stock_df.empty:
        for _, row in low_stock_df.iterrows():
            st.error(f"**{row['Rice_Variety']} ({row['SKU']})**\n\nOnly **{int(row['Stock_Count'])}** bags remaining!")
    else:
        st.success("✅ All stock volumes sit comfortably above baseline thresholds.")
