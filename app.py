import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner (Drive Connected)")

# --- 1. SETUP GOOGLE DRIVE ---
# We use the same secret key you added earlier
try:
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)
    else:
        st.error("⚠️ Secrets Error: 'gcp_service_account' not found in Streamlit secrets.")
        st.stop()
except Exception as e:
    st.error(f"Authentication Error: {e}")
    st.stop()

# --- 2. SETUP AI ---
model = None
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. LOAD DATA FROM DRIVE (Fast & Cached) ---
@st.cache_data(ttl=3600) # Data stays in memory for 1 hour
def load_data_from_drive():
    try:
        # Search for the specific filename
        query = "name = 'latest_nse_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            return None
        
        # Download the file content
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        df = pd.read_csv(downloaded)
        return df
    except Exception as e:
        st.error(f"Drive Read Error: {e}")
        return None

# --- 4. DASHBOARD UI ---
with st.spinner("Connecting to your 2TB Google Drive..."):
    data = load_data_from_drive()

if data is None:
    st.error("❌ 'latest_nse_data.csv' not found in Drive. Please run the GitHub Action once.")
else:
    # Success! Show timestamp if available
    st.success("✅ Data loaded from Google Drive instantly!")
    
    # Clean Column Names
    data.columns = [c.replace('"', '').strip() for c in data.columns]
    
    # Identify Delivery Column
    target_col = "%DlyQttoTradedQty"
    if target_col not in data.columns:
        possible = [c for c in data.columns if "DlyQt" in c or "DELIV" in c]
        if possible: target_col = possible[0]
        
    if target_col in data.columns:
        # Ensure numeric
        data[target_col] = pd.to_numeric(data[target_col], errors='coerce').fillna(0)
        
        # --- BUCKET TABS ---
        st.divider()
        st.subheader("📊 Market Delivery Buckets")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "🔥 80-100% (Strong)", 
            "💎 60-80% (High)", 
            "✅ 40-60% (Medium)", 
            "⚠️ <40% (Weak)"
        ])
        
        # Filter Logic
        cols_to_show = ['SYMBOL', 'SERIES', 'CLOSE_PRICE', target_col]
        
        with tab1:
            df_80 = data[data[target_col] >= 80].sort_values(by=target_col, ascending=False)
            st.dataframe(df_80[cols_to_show], use_container_width=True)
            
        with tab2:
            df_60 = data[(data[target_col] >= 60) & (data[target_col] < 80)].sort_values(by=target_col, ascending=False)
            st.dataframe(df_60[cols_to_show], use_container_width=True)
            
        with tab3:
            df_40 = data[(data[target_col] >= 40) & (data[target_col] < 60)].sort_values(by=target_col, ascending=False)
            st.dataframe(df_40[cols_to_show], use_container_width=True)

        with tab4:
            df_low = data[data[target_col] < 40].sort_values(by=target_col, ascending=False)
            st.dataframe(df_low[cols_to_show], use_container_width=True)

    # --- AI ANALYSIS ---
    if model:
        st.divider()
        st.subheader("🤖 AI Stock Decoder")
        col1, col2 = st.columns([1, 3])
        with col1:
            ticker_input = st.text_input("Analyze Ticker (e.g. TCS)", "").upper()
            analyze_btn = st.button("Decode with AI")
        
        with col2:
            if analyze_btn and ticker_input:
                stock_data = data[data['SYMBOL'] == ticker_input]
                if not stock_data.empty:
                    del_val = stock_data[target_col].iloc[0]
                    prompt = (f"The stock {ticker_input} has a delivery percentage of {del_val}%. "
                              "Is this considered high accumulation? What does it mean for a swing trader?")
                    with st.spinner("AI thinking..."):
                        response = model.generate_content(prompt)
                        st.markdown(response.text)
                else:
                    st.warning("Ticker not found in today's list.")
