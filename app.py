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

# --- HELPER: COLUMN NORMALIZER ---
def clean_column_names(df):
    # Remove spaces and quotes
    df.columns = [str(c).replace('"', '').strip() for c in df.columns]
    return df

# --- 3. DATA LOADING (MEMORY OPTIMIZED) ---

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

@st.cache_data(ttl=3600, show_spinner="Loading History (Lite Mode)...")
def load_history_data():
    try:
        # Find the NEWEST file if duplicates exist
        query = "name = 'nse_history_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        files = results.get('files', [])
        
        if not files:
            st.error("❌ 'nse_history_data.csv' not found in Drive.")
            return None
            
        # Sort by creation time to get the latest one
        files.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
        file_id = files[0]['id'] # Pick the newest one
        
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        # --- MEMORY OPTIMIZATION: Read only specific columns ---
        # We try to read specific columns based on your screenshot
        # SYMBOL, CLOSE_PR, DELIV_PER, Trade_Date
        try:
            df = pd.read_csv(
                downloaded, 
                usecols=lambda c: c in ['SYMBOL', 'CLOSE_PR', 'CLOSE_PRICE', 'DELIV_PER', 'DELIVERY_PER', 'Trade_Date', 'DATE1'],
                low_memory=False
            )
        except ValueError:
            # If usecols fails (column names differ), read everything (fallback)
            downloaded.seek(0)
            df = pd.read_csv(downloaded, low_memory=False)

        df = clean_column_names(df)
        
        # Normalize Date
        date_col = next((c for c in ['Trade_Date', 'DATE1', 'Date'] if c in df.columns), None)
        if date_col:
            df['Trade_Date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        # Normalize Close Price
        close_col = next((c for c in ['CLOSE_PR', 'CLOSE_PRICE'] if c in df.columns), None)
        if close_col:
            df.rename(columns={close_col: 'CLOSE_PRICE'}, inplace=True)
            
        # Normalize Delivery
        deliv_col = next((c for c in ['DELIV_PER', 'DELIVERY_PER'] if c in df.columns), None)
        if deliv_col:
            df.rename(columns={deliv_col: 'DELIV_PER'}, inplace=True)

        return df
        
    except Exception as e:
        st.error(f"❌ Error loading history: {e}")
        return None

# --- 4. MAIN DASHBOARD ---

daily_data = load_daily_data()
history_data = load_history_data() # Loads in background

if daily_data is None:
    st.error("❌ Daily data missing.")
    st.stop()

daily_data = clean_column_names(daily_data)

# Find Delivery Col in Daily Data
daily_deliv_col = next((c for c in daily_data.columns if "DELIV" in c and ("PER" in c or "%" in c)), None)
if not daily_deliv_col:
     daily_deliv_col = next((c for c in daily_data.columns if "%" in c), None)

if daily_deliv_col:
    daily_data[daily_deliv_col] = pd.to_numeric(daily_data[daily_deliv_col], errors='coerce').fillna(0)

    # --- UI ---
    st.subheader("🔍 Smart Stock Analyzer")
    col_search, col_stats = st.columns([1, 3])
    
    with col_search:
        search_ticker = st.text_input("Enter Ticker (e.g. TCS)", "").upper().strip()

    if search_ticker:
        # 1. Today's Stats
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        with col_stats:
            if not row.empty:
                val = row[daily_deliv_col].iloc[0]
                price = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in daily_data.columns else "-"
                color = "green" if val > 60 else "orange" if val > 40 else "red"
                st.markdown(f"### Today: ₹{price} | Delivery: :{color}[{val}%]")
            else:
                st.warning("Not in today's list.")

        # 2. History Chart
        if history_data is not None:
            if 'Trade_Date' in history_data.columns and 'DELIV_PER' in history_data.columns:
                stock_hist = history_data[history_data['SYMBOL'] == search_ticker].sort_values('Trade_Date')
                
                if not stock_hist.empty:
                    # Fix numeric types
                    stock_hist['DELIV_PER'] = pd.to_numeric(stock_hist['DELIV_PER'], errors='coerce')
                    stock_hist['CLOSE_PRICE'] = pd.to_numeric(stock_hist['CLOSE_PRICE'], errors='coerce')
                    
                    fig = go.Figure()
                    # Bars
                    fig.add_trace(go.Bar(
                        x=stock_hist['Trade_Date'], y=stock_hist['DELIV_PER'],
                        name='Delivery %', marker_color='rgba(50, 171, 96, 0.6)', yaxis='y2'
                    ))
                    # Line
                    fig.add_trace(go.Scatter(
                        x=stock_hist['Trade_Date'], y=stock_hist['CLOSE_PRICE'],
                        name='Price', line=dict(color='black', width=2)
                    ))
                    
                    fig.update_layout(
                        title=f"{search_ticker} - 1 Year Trend",
                        yaxis=dict(title="Price"),
                        yaxis2=dict(title="Delivery %", overlaying="y", side="right", range=[0, 100]),
                        height=400, hovermode="x unified"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info(f"No history found for {search_ticker}")
            else:
                st.error(f"Missing Columns in History. Found: {list(history_data.columns)}")
        else:
            st.info("Loading history file...")

    # --- SCANNER ---
    st.divider()
    st.subheader("📊 Scanner")
    
    cols = ['SYMBOL', 'CLOSE_PRICE', daily_deliv_col]
    cols = [c for c in cols if c in daily_data.columns]
    
    tab1, tab2 = st.tabs(["🔥 High Delivery (>60%)", "⚠️ Low Delivery (<40%)"])
    with tab1:
        st.dataframe(daily_data[daily_data[daily_deliv_col] > 60][cols].sort_values(daily_deliv_col, ascending=False), use_container_width=True)
    with tab2:
        st.dataframe(daily_data[daily_data[daily_deliv_col] < 40][cols].sort_values(daily_deliv_col, ascending=True), use_container_width=True)

    # --- AI ---
    st.divider()
    st.subheader("🤖 AI Analysis")
    if st.button("Analyze Ticker") and search_ticker and model:
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        if not row.empty:
             val = row[daily_deliv_col].iloc[0]
             pr = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in row else "N/A"
             prompt = f"Analyze {search_ticker}. Price {pr}, Delivery {val}%. Bullish or Bearish for swing trade? Short answer."
             st.write(model.generate_content(prompt).text)
