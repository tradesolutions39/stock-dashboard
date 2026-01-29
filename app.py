import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
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
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            test_model.generate_content("test") 
            model = test_model
        except:
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

# --- HELPER: ROBUST COLUMN FINDER ---
def find_delivery_column(df):
    df.columns = [str(c).replace('"', '').strip().upper() for c in df.columns]
    priorities = ["%DLYQTTO TRADEDQTY", "DELIV_PER", "PCT_DELIV", "DELIVERY_PER", "DELIV_QTY"] # Added DELIV_QTY as fallback
    for p in priorities:
        if p in df.columns:
            return p
    for c in df.columns:
        if "DELIV" in c and ("PER" in c or "%" in c):
            return c
    return None

def standardize_date_column(df):
    df.columns = [str(c).replace('"', '').strip() for c in df.columns]
    candidates = ['Trade_Date', 'DATE1', 'TRADEDDATE', 'Date', 'TIMESTAMP', 'date']
    
    found_col = None
    for col in df.columns:
        if col in candidates or col.upper() in [c.upper() for c in candidates]:
            found_col = col
            break
    
    if found_col:
        df.rename(columns={found_col: 'Trade_Date'}, inplace=True)
        df['Trade_Date'] = pd.to_datetime(df['Trade_Date'], errors='coerce')
        return True
    return False

# --- 3. LOAD DATA FUNCTIONS (WITH CACHE CLEARING) ---
if st.sidebar.button("🛠️ Reset/Refresh Data"):
    st.cache_data.clear()
    st.rerun()

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
        
        df = pd.read_csv(downloaded)
        standardize_date_column(df) # Apply fix
        return df
    except:
        return None

# --- 4. MAIN DASHBOARD ---
with st.spinner("Syncing with Cloud Database..."):
    daily_data = load_daily_data()
    history_data = load_history_data()

if daily_data is None:
    st.error("❌ 'latest_nse_data.csv' not found. Please run the Daily Action.")
    st.stop()

daily_col = find_delivery_column(daily_data)

if daily_col:
    daily_data[daily_col] = pd.to_numeric(daily_data[daily_col], errors='coerce').fillna(0)
    
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
                val = today_row[daily_col].iloc[0]
                price = today_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in daily_data.columns else "-"
                color = "green" if val > 60 else "orange" if val > 40 else "red"
                st.markdown(f"### Today: ₹{price} | Delivery: :{color}[{val}%]")
            else:
                st.warning(f"Ticker '{search_ticker}' not found in today's active list.")

        # B. Show Historical Chart (CRASH PROOF)
        if history_data is not None:
            # Check if columns exist BEFORE filtering
            if 'Trade_Date' not in history_data.columns:
                st.error(f"⚠️ Date Column missing in History File. Found: {list(history_data.columns)}")
                st.info("Try clicking 'Reset Data' in sidebar.")
            else:
                stock_hist = history_data[history_data['SYMBOL'] == search_ticker].copy()
                
                if not stock_hist.empty:
                    stock_hist = stock_hist.sort_values('Trade_Date')
                    hist_col = find_delivery_column(stock_hist)
                    
                    if hist_col:
                        stock_hist[hist_col] = pd.to_numeric(stock_hist[hist_col], errors='coerce')
                        
                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            x=stock_hist['Trade_Date'],
                            y=stock_hist[hist_col],
                            name='Delivery %',
                            marker_color='rgba(50, 171, 96, 0.6)',
                            yaxis='y2'
                        ))

                        price_col = next((c for c in stock_hist.columns if "CLOSE" in c), None)
                        if price_col:
                            fig.add_trace(go.Scatter(
                                x=stock_hist['Trade_Date'],
                                y=stock_hist[price_col],
                                name='Price',
                                line=dict(color='rgb(0, 0, 0)', width=2)
                            ))

                        fig.update_layout(
                            title=f'{search_ticker} - Price vs Delivery Trend (1 Year)',
                            yaxis=dict(title='Price', side='left'),
                            yaxis2=dict(title='Delivery %', side='right', overlaying='y', range=[0, 100]),
                            legend=dict(x=0, y=1.1, orientation='h'),
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("History file loaded, but Delivery Column not found.")
                else:
                    st.info(f"No history found for {search_ticker}. The archive might be incomplete.")
        else:
            st.warning("History file is loading... (If this persists, click 'Reset Data')")

    # --- UI SECTION 2: SCANNER ---
    st.divider()
    st.subheader("📊 Market Delivery Scanner")
    tab1, tab2, tab3 = st.tabs(["🔥 Strong (>80%)", "💎 Accumulation (60-80%)", "⚠️ Weak (<40%)"])
    
    cols_to_show = ['SYMBOL', 'CLOSE_PRICE', daily_col]
    cols_to_show = [c for c in cols_to_show if c in daily_data.columns]
    
    with tab1:
        st.dataframe(daily_data[daily_data[daily_col] >= 80][cols_to_show].sort_values(daily_col, ascending=False), use_container_width=True)
    with tab2:
        st.dataframe(daily_data[(daily_data[daily_col] >= 60) & (daily_data[daily_col] < 80)][cols_to_show].sort_values(daily_col, ascending=False), use_container_width=True)
    with tab3:
        st.dataframe(daily_data[daily_data[daily_col] < 40][cols_to_show].sort_values(daily_col, ascending=False), use_container_width=True)

    # --- UI SECTION 3: AI DECODER ---
    st.divider()
    st.subheader("🤖 AI Stock Decoder")
    ai_default = search_ticker if search_ticker else ""
    col_ai_in, col_ai_out = st.columns([1, 4])
    
    with col_ai_in:
        ai_ticker = st.text_input("Analyze Ticker", value=ai_default, key="ai_input").upper().strip()
        btn_analyze = st.button("Generate Report")
        
    with col_ai_out:
        if btn_analyze and ai_ticker and model:
            row = daily_data[daily_data['SYMBOL'] == ai_ticker]
            if not row.empty:
                del_p = row[daily_col].iloc[0]
                price = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in row else "N/A"
                prompt = f"Analyze {ai_ticker}. Price: {price}, Delivery %: {del_p}%. Is this high accumulation? Short verdict."
                with st.spinner(f"AI Analyzing {ai_ticker}..."):
                    st.markdown(model.generate_content(prompt).text)
            else:
                st.warning("Data not found for analysis.")
else:
    st.error(f"CRITICAL: Could not find any Delivery Percentage column. Columns found: {list(daily_data.columns)}")
