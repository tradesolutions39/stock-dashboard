import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
import plotly.express as px
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner + Historical Archive")

# --- 1. SETUP AI ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        try:
            # Try Flash model first
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            test_model.generate_content("test") 
            model = test_model
        except:
            # Fallback
            available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if available: model = genai.GenerativeModel(available[0])
except Exception:
    pass

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
except Exception as e:
    st.error(f"Authentication Error: {e}")
    st.stop()

# --- 3. LOAD DATA FUNCTIONS ---

# Function A: Load Today's Data (Fast)
@st.cache_data(ttl=3600)
def load_daily_data():
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

# Function B: Load History Archive (Big File)
@st.cache_data(ttl=3600)
def load_history_data():
    try:
        query = "name = 'nse_history_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files: return None
        
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        # Read CSV but optimize memory
        df = pd.read_csv(downloaded)
        
        # Clean columns immediately
        df.columns = [c.replace('"', '').strip() for c in df.columns]
        
        # Parse Dates
        if 'Trade_Date' in df.columns:
            df['Trade_Date'] = pd.to_datetime(df['Trade_Date'])
            
        return df
    except:
        return None

# --- 4. DATA LOADING & CLEANING ---
with st.spinner("Syncing with Cloud Database..."):
    daily_data = load_daily_data()
    # Load history in background (cached)
    history_data = load_history_data()

if daily_data is None:
    st.error("❌ 'latest_nse_data.csv' not found. Please run the Daily Action.")
    st.stop()

# Clean Daily Data
daily_data.columns = [c.replace('"', '').strip() for c in daily_data.columns]

# Find Percentage Column
target_col = "%DlyQttoTradedQty"
if target_col not in daily_data.columns:
    possible = [c for c in daily_data.columns if "%" in c or "PER" in c.upper()]
    if possible: target_col = possible[0]
    else: target_col = None

if target_col:
    daily_data[target_col] = pd.to_numeric(daily_data[target_col], errors='coerce').fillna(0)
    
    # --- UI SECTION 1: SEARCH & CHART ---
    st.subheader("🔍 Smart Stock Analyzer")
    
    col_search, col_stats = st.columns([1, 3])
    with col_search:
        search_ticker = st.text_input("Enter Ticker (e.g. RELIANCE)", "").upper().strip()
    
    if search_ticker:
        # A. Show Today's Snapshot
        today_row = daily_data[daily_data['SYMBOL'] == search_ticker]
        
        with col_stats:
            if not today_row.empty:
                val = today_row[target_col].iloc[0]
                price = today_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in daily_data.columns else "-"
                
                # Dynamic Color
                color = "green" if val > 60 else "orange" if val > 40 else "red"
                st.markdown(f"### Today: ₹{price} | Delivery: :{color}[{val}%]")
            else:
                st.warning(f"Ticker '{search_ticker}' not found in today's active list.")

        # B. Show Historical Chart
        if history_data is not None:
            stock_hist = history_data[history_data['SYMBOL'] == search_ticker].sort_values('Trade_Date')
            
            if not stock_hist.empty:
                # Identify History Columns
                h_target_col = "%DlyQttoTradedQty"
                if h_target_col not in stock_hist.columns:
                    possible = [c for c in stock_hist.columns if "%" in c]
                    if possible: h_target_col = possible[0]
                
                if h_target_col:
                    # Create Dual-Axis Chart
                    fig = go.Figure()

                    # Bar Chart (Delivery %)
                    fig.add_trace(go.Bar(
                        x=stock_hist['Trade_Date'],
                        y=stock_hist[h_target_col],
                        name='Delivery %',
                        marker_color='rgba(50, 171, 96, 0.6)',
                        yaxis='y2'
                    ))

                    # Line Chart (Price)
                    fig.add_trace(go.Scatter(
                        x=stock_hist['Trade_Date'],
                        y=stock_hist['CLOSE_PRICE'],
                        name='Price',
                        line=dict(color='rgb(0, 0, 0)', width=2)
                    ))

                    # Layout
                    fig.update_layout(
                        title=f'{search_ticker} - Price vs Delivery Trend (1 Year)',
                        yaxis=dict(title='Price', side='left'),
                        yaxis2=dict(title='Delivery %', side='right', overlaying='y', range=[0, 100]),
                        legend=dict(x=0, y=1.1, orientation='h'),
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Historical Delivery column not found.")
            else:
                st.info(f"No historical data found for {search_ticker} in archive.")
        else:
            st.warning("History file is loading or missing. Only today's data is available.")

    # --- UI SECTION 2: SCANNER ---
    st.divider()
    st.subheader("📊 Market Delivery Scanner")
    
    tab1, tab2, tab3 = st.tabs(["🔥 Strong (>80%)", "💎 Accumulation (60-80%)", "⚠️ Weak (<40%)"])
    cols_to_show = ['SYMBOL', 'CLOSE_PRICE', target_col]
    cols_to_show = [c for c in cols_to_show if c in daily_data.columns]
    
    with tab1:
        st.dataframe(daily_data[daily_data[target_col] >= 80][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)
    with tab2:
        st.dataframe(daily_data[(daily_data[target_col] >= 60) & (daily_data[target_col] < 80)][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)
    with tab3:
        st.dataframe(daily_data[daily_data[target_col] < 40][cols_to_show].sort_values(target_col, ascending=False), use_container_width=True)

    # --- UI SECTION 3: AI DECODER ---
    st.divider()
    st.subheader("🤖 AI Stock Decoder")
    
    # Auto-fill ticker
    ai_default = search_ticker if search_ticker else ""
    
    col_ai_in, col_ai_out = st.columns([1, 4])
    with col_ai_in:
        ai_ticker = st.text_input("Analyze Ticker", value=ai_default, key="ai_input").upper().strip()
        btn_analyze = st.button("Generate Report")
        
    with col_ai_out:
        if btn_analyze and ai_ticker and model:
            # Check if we have data (Try Today's data first)
            row = daily_data[daily_data['SYMBOL'] == ai_ticker]
            
            if not row.empty:
                del_p = row[target_col].iloc[0]
                price = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in row else "N/A"
                
                prompt = (
                    f"Analyze the Indian stock '{ai_ticker}'. "
                    f"Today's Price: {price}, Delivery %: {del_p}%. "
                    "Is this high delivery percentage a sign of 'Smart Money' accumulation or a trap? "
                    "Provide a very short, professional verdict for a swing trader."
                )
                
                with st.spinner(f"AI Analyzing {ai_ticker}..."):
                    st.markdown(model.generate_content(prompt).text)
            else:
                st.warning("Data not found for analysis.")
