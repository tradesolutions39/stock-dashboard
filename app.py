import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner (Drive Connected)")

# --- 1. ROBUST AI SETUP (Self-Healing) ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # Ask Google: "What models do you have?"
        available_models = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
        except:
            pass # If listing fails, we will try defaults
            
        # Smart Selection Logic
        target_model = "models/gemini-pro" # Default safe option
        if 'models/gemini-1.5-flash' in available_models:
            target_model = 'models/gemini-1.5-flash'
        elif 'models/gemini-1.5-pro' in available_models:
            target_model = 'models/gemini-1.5-pro'
            
        model = genai.GenerativeModel(target_model)
    else:
        st.warning("⚠️ AI Key missing. Check 'GEMINI_API_KEY' in secrets.")
except Exception as e:
    st.warning(f"AI functionality disabled due to error: {e}")

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
        st.error("⚠️ Secrets Error: 'gcp_service_account' not found.")
        st.stop()
except Exception as e:
    st.error(f"Authentication Error: {e}")
    st.stop()

# --- 3. LOAD DATA FROM DRIVE ---
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
    except Exception as e:
        st.error(f"Drive Read Error: {e}")
        return None

# --- 4. DASHBOARD UI ---
with st.spinner("Accessing Cloud Database..."):
    data = load_data_from_drive()

if data is None:
    st.error("❌ Data file not found. Please run the GitHub Action.")
else:
    # Success Message
    st.success(f"✅ Market Data Loaded Successfully! ({len(data)} stocks)")
    
    # Cleaning
    data.columns = [c.replace('"', '').strip() for c in data.columns]
    
    # Column Finder
    target_col = "%DlyQttoTradedQty"
    if target_col not in data.columns:
        possible = [c for c in data.columns if "DlyQt" in c or "DELIV" in c]
        if possible: target_col = possible[0]
        
    if target_col in data.columns:
        data[target_col] = pd.to_numeric(data[target_col], errors='coerce').fillna(0)
        
        # --- BUCKETS ---
        st.divider()
        tab1, tab2, tab3 = st.tabs(["🔥 Strong Buying (>80%)", "💎 Accumulation (60-80%)", "⚠️ Weak (<40%)"])
        
        cols = ['SYMBOL', 'CLOSE_PRICE', target_col]
        
        with tab1:
            st.dataframe(data[data[target_col] >= 80][cols].sort_values(by=target_col, ascending=False), use_container_width=True)
        with tab2:
            st.dataframe(data[(data[target_col] >= 60) & (data[target_col] < 80)][cols].sort_values(by=target_col, ascending=False), use_container_width=True)
        with tab3:
            st.dataframe(data[data[target_col] < 40][cols].sort_values(by=target_col, ascending=False), use_container_width=True)

    # --- AI ANALYSIS SECTION ---
    st.divider()
    st.subheader("🤖 AI Stock Decoder")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        ticker_input = st.text_input("Enter Ticker (e.g. TCS)", "").upper().strip()
        analyze_btn = st.button("Decode with AI")
    
    with col2:
        if analyze_btn and ticker_input:
            if not model:
                st.error("AI Model is not connected. Check API Key.")
            else:
                # Find data for this ticker
                stock_row = data[data['SYMBOL'] == ticker_input]
                
                if not stock_row.empty:
                    del_per = stock_row[target_col].iloc[0]
                    price = stock_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in stock_row else "N/A"
                    
                    prompt = (
                        f"Analyze the Indian stock {ticker_input}. "
                        f"It has a very high Delivery Percentage of {del_per}% at a price of {price}. "
                        "Explain to a beginner investor: Does this indicate 'Smart Money' accumulation? "
                        "What are the risks? Keep it short and professional."
                    )
                    
                    with st.spinner(f"AI is analyzing {ticker_input}..."):
                        try:
                            response = model.generate_content(prompt)
                            st.markdown(response.text)
                        except Exception as e:
                            st.error(f"AI Error: {e}")
                else:
                    st.warning(f"Ticker '{ticker_input}' not found in today's list.")
