import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
import plotly.express as px
from nselib import capital_market
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner + History")

# --- 1. SETUP AI ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        try:
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            test_model.generate_content("test") 
            model = test_model
        except:
            available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if available: model = genai.GenerativeModel(available[0])
except Exception as e:
    st.warning(f"AI disabled: {e}")

# --- 2. SETUP GOOGLE DRIVE ---
try:
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)
    else:
        st.error("⚠️ Secrets Error: 'gcp_service_account' missing.")
        st.stop()
except Exception:
    st.stop()

# --- 3. LOAD TODAY'S DATA ---
@st.cache_data(ttl=3600)
def load_data_from_drive():
    try:
        query = "name = 'latest_nse_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files: return None
        
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        return pd.read_csv(downloaded)
    except:
        return None

# --- 4. FETCH HISTORY (ON DEMAND) ---
@st.cache_data(ttl=3600)
def fetch_history(symbol):
    try:
        # Fetch last 1 year data live from NSE
        df = capital_market.price_volume_and_deliverable_position_data(symbol=symbol, period='1Y')
        if df is None or df.empty: return None
        
        # Clean Data
        df.columns = [c.replace('"', '').strip() for c in df.columns]
        
        # Parse Dates
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%Y', errors='coerce')
        df = df.sort_values('Date')
        
        # Fix Numeric Columns
        target_col = "%DlyQttoTradedQty"
        if target_col not in df.columns:
            possible = [c for c in df.columns if "%" in c or "PER" in c.upper()]
            if possible: target_col = possible[0]
            
        if target_col:
            df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
            df['ClosePrice'] = pd.to_numeric(df['ClosePrice'], errors='coerce')
            
        return df, target_col
    except Exception as e:
        return None, None

# --- 5. DASHBOARD UI ---
data = load_data_from_drive()

if data is not None:
    # Clean Column Names
    data.columns = [c.replace('"', '').strip() for c in data.columns]
    
    # Identify Percentage Column
    target_col = "%DlyQttoTradedQty"
    if target_col not in data.columns:
        possible = [c for c in data.columns if "%" in c or "PER" in c.upper()]
        if possible: target_col = possible[0]
        else: target_col = None

    if target_col:
        data[target_col] = pd.to_numeric(data[target_col], errors='coerce').fillna(0)
        
        # --- TOP SECTION: SEARCH & HISTORY ---
        st.subheader("🔍 Stock Deep Dive")
        col_search, col_chart = st.columns([1, 2])
        
        with col_search:
            search_ticker = st.text_input("Search Ticker (e.g. INFJY)", "").upper().strip()
            
            if search_ticker:
                # 1. Show Today's Stats
                stock_row = data[data['SYMBOL'] == search_ticker]
                if not stock_row.empty:
                    val = stock_row[target_col].iloc[0]
                    price = stock_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in data.columns else "-"
                    st.info(f"**Today:** Price ₹{price} | Delivery: **{val}%**")
                else:
                    st.warning("Not in today's list.")

        # --- HISTORICAL CHART SECTION ---
        if search_ticker:
            with st.spinner(f"Fetching 1-Year History for {search_ticker}..."):
                hist_df, hist_col = fetch_history(search_ticker)
                
                if hist_df is not None:
                    # Create Chart: Price vs Delivery %
                    fig = px.line(hist_df, x='Date', y='ClosePrice', title=f"{search_ticker} - 1 Year Price Trend")
                    
                    # Add Delivery Bars
                    fig.add_bar(x=hist_df['Date'], y=hist_df[hist_col], name='Delivery %', opacity=0.3, yaxis='y2')
                    
                    # Dual Axis Layout
                    fig.update_layout(
                        yaxis=dict(title="Price", side="left"),
                        yaxis2=dict(title="Delivery %", side="right", overlaying="y", range=[0, 100]),
                        legend=dict(x=0, y=1.1, orientation="h")
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("Could not fetch history from NSE.")

        # --- LOWER SECTION: SCANNER ---
        st.divider()
        st.subheader("📊 Today's Market Scanner")
        
        tab1, tab2, tab3 = st.tabs(["🔥 Strong (>80%)", "💎 Accumulation (60-80%)", "⚠️ Weak (<40%)"])
        cols_to_show = ['SYMBOL', 'SERIES', 'CLOSE_PRICE', target_col]
        cols_to_show = [c for c in cols_to_show if c in data.columns]

        with tab1:
            st.dataframe(data[data[target_col] >= 80][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)
        with tab2:
            st.dataframe(data[(data[target_col] >= 60) & (data[target_col] < 80)][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)
        with tab3:
            st.dataframe(data[data[target_col] < 40][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)

        # --- AI SECTION ---
        st.divider()
        st.subheader("🤖 AI Stock Decoder")
        ai_ticker = st.text_input("Ticker to Decode", value=search_ticker if search_ticker else "").upper()
        if st.button("Generate Report") and ai_ticker and model:
            row = data[data['SYMBOL'] == ai_ticker]
            if not row.empty:
                del_p = row[target_col].iloc[0]
                prompt = f"Analyze {ai_ticker} (Delivery: {del_p}%). Is this 'Smart Money' buying? Short outlook?"
                st.write(model.generate_content(prompt).text)
            else:
                st.warning("Ticker not found in data.")
