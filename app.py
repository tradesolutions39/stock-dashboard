import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
import plotly.graph_objects as go
import yfinance as yf

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner + Fundamentals")

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
    df.columns = [str(c).replace('"', '').strip() for c in df.columns]
    return df

# --- 3. DATA LOADING ---

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
        query = "name = 'nse_history_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        files = results.get('files', [])
        
        if not files: return None
            
        files.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
        file_id = files[0]['id']
        
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        try:
            df = pd.read_csv(
                downloaded, 
                usecols=lambda c: c in ['SYMBOL', 'CLOSE_PR', 'CLOSE_PRICE', 'DELIV_PER', 'DELIVERY_PER', 'Trade_Date', 'DATE1'],
                low_memory=False
            )
        except ValueError:
            downloaded.seek(0)
            df = pd.read_csv(downloaded, low_memory=False)

        df = clean_column_names(df)
        
        date_col = next((c for c in ['Trade_Date', 'DATE1', 'Date'] if c in df.columns), None)
        if date_col:
            df['Trade_Date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        close_col = next((c for c in ['CLOSE_PR', 'CLOSE_PRICE'] if c in df.columns), None)
        if close_col:
            df.rename(columns={close_col: 'CLOSE_PRICE'}, inplace=True)
            
        deliv_col = next((c for c in ['DELIV_PER', 'DELIVERY_PER'] if c in df.columns), None)
        if deliv_col:
            df.rename(columns={deliv_col: 'DELIV_PER'}, inplace=True)

        return df
    except Exception as e:
        st.error(f"❌ Error loading history: {e}")
        return None

# --- NEW: ADVANCED FUNDAMENTALS (GROWTH CHECK) ---
@st.cache_data(ttl=86400)
def get_fundamentals(ticker):
    try:
        stock = yf.Ticker(f"{ticker}.NS")
        info = stock.info
        
        # Get Financials for Trend Analysis (Annual)
        fin = stock.financials
        
        sales_growth = "N/A"
        opm_growth = "N/A"
        eps_growth = "N/A"
        
        if not fin.empty and len(fin.columns) >= 2:
            # Recent Year vs Previous Year
            curr = fin.iloc[:, 0]
            prev = fin.iloc[:, 1]
            
            # 1. Sales Trend
            if 'Total Revenue' in fin.index:
                sales_growth = "⬆️ Rising" if curr['Total Revenue'] > prev['Total Revenue'] else "⬇️ Falling"
            
            # 2. EPS Trend
            if 'Basic EPS' in fin.index:
                eps_growth = "⬆️ Rising" if curr['Basic EPS'] > prev['Basic EPS'] else "⬇️ Falling"
                
            # 3. OPM Trend (Operating Income / Revenue)
            if 'Operating Income' in fin.index and 'Total Revenue' in fin.index:
                opm_curr = (curr['Operating Income'] / curr['Total Revenue']) * 100
                opm_prev = (prev['Operating Income'] / prev['Total Revenue']) * 100
                opm_growth = "⬆️ Rising" if opm_curr > opm_prev else "⬇️ Falling"

        data = {
            "PE Ratio": info.get("trailingPE", None),
            "ROE": info.get("returnOnEquity", None),
            "Market Cap (Cr)": info.get("marketCap", 0) / 10000000 if info.get("marketCap") else 0,
            "Sector": info.get("sector", "Unknown"),
            "Sales Trend": sales_growth,
            "OPM Trend": opm_growth,
            "EPS Trend": eps_growth
        }
        return data
    except:
        return None

# --- 4. MAIN DASHBOARD ---

daily_data = load_daily_data()
history_data = load_history_data()

if daily_data is None:
    st.error("❌ Daily data missing.")
    st.stop()

daily_data = clean_column_names(daily_data)

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
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        
        # 1. Technical Stats
        if not row.empty:
            val = row[daily_deliv_col].iloc[0]
            price = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in daily_data.columns else "-"
            
            if val > 80: color_txt = "green"
            elif val > 60: color_txt = "orange"
            else: color_txt = "red"
            
            with col_stats:
                st.markdown(f"### Today: ₹{price} | Delivery: :{color_txt}[{val}%]")
        
        # 2. FUNDAMENTAL HEALTH CHECK (UPDATED)
        with st.expander(f"📊 Fundamental Health Check: {search_ticker}", expanded=True):
            fund_data = get_fundamentals(search_ticker)
            if fund_data:
                # Row 1: Basic Stats
                c1, c2, c3, c4 = st.columns(4)
                pe = fund_data['PE Ratio']
                pe_color = "green" if pe and pe < 25 else "red"
                c1.metric("PE Ratio", f"{round(pe, 2)}" if pe else "N/A", delta_color="inverse")
                
                roe = fund_data['ROE']
                c2.metric("ROE", f"{round(roe * 100, 2)}%" if roe else "N/A")
                
                c3.metric("Market Cap", f"₹{int(fund_data['Market Cap (Cr)'])} Cr")
                c4.metric("Sector", fund_data['Sector'])
                
                st.divider()
                
                # Row 2: GROWTH TRENDS
                st.caption("Year-on-Year Growth Trends (Financials)")
                g1, g2, g3 = st.columns(3)
                
                g1.metric("Sales Growth", fund_data['Sales Trend'])
                g2.metric("OPM (Margins)", fund_data['OPM Trend'])
                g3.metric("EPS (Profit)", fund_data['EPS Trend'])
                
            else:
                st.info("Fundamental data not available for this ticker.")

        # 3. History Chart
        if history_data is not None:
            if 'Trade_Date' in history_data.columns and 'DELIV_PER' in history_data.columns:
                stock_hist = history_data[history_data['SYMBOL'] == search_ticker].sort_values('Trade_Date')
                
                if not stock_hist.empty:
                    stock_hist['DELIV_PER'] = pd.to_numeric(stock_hist['DELIV_PER'], errors='coerce')
                    stock_hist['CLOSE_PRICE'] = pd.to_numeric(stock_hist['CLOSE_PRICE'], errors='coerce')
                    
                    colors = []
                    for x in stock_hist['DELIV_PER']:
                        if x >= 80: colors.append('rgba(0, 100, 0, 0.8)')
                        elif x >= 60: colors.append('rgba(50, 205, 50, 0.7)')
                        elif x >= 40: colors.append('rgba(128, 128, 128, 0.6)')
                        else: colors.append('rgba(255, 0, 0, 0.6)')

                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=stock_hist['Trade_Date'], y=stock_hist['DELIV_PER'],
                        name='Delivery %', marker_color=colors, yaxis='y2'
                    ))
                    fig.add_trace(go.Scatter(
                        x=stock_hist['Trade_Date'], y=stock_hist['CLOSE_PRICE'],
                        name='Price', line=dict(color='black', width=2)
                    ))
                    fig.update_layout(
                        title=f"{search_ticker} - Delivery Trend",
                        yaxis=dict(title="Price"),
                        yaxis2=dict(title="Delivery %", overlaying="y", side="right", range=[0, 100]),
                        height=400, hovermode="x unified", showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info(f"No history found for {search_ticker}")

    # --- SCANNER ---
    st.divider()
    st.subheader("📊 Scanner")
    
    cols = ['SYMBOL', 'CLOSE_PRICE', daily_deliv_col]
    cols = [c for c in cols if c in daily_data.columns]
    
    df_clean = daily_data[daily_data[daily_deliv_col] < 99.9]
    
    tab1, tab2, tab3 = st.tabs(["🔥 High (80-99%)", "💎 Medium (60-80%)", "⚠️ Low (<40%)"])
    
    with tab1:
        df_high = df_clean[df_clean[daily_deliv_col] >= 80]
        st.dataframe(df_high[cols].sort_values(daily_deliv_col, ascending=False), use_container_width=True)
        
    with tab2:
        df_med = df_clean[(df_clean[daily_deliv_col] >= 60) & (df_clean[daily_deliv_col] < 80)]
        st.dataframe(df_med[cols].sort_values(daily_deliv_col, ascending=False), use_container_width=True)
        
    with tab3:
        df_low = df_clean[df_clean[daily_deliv_col] < 40]
        st.dataframe(df_low[cols].sort_values(daily_deliv_col, ascending=True), use_container_width=True)

    # --- AI ANALYSIS ---
    st.divider()
    st.subheader("🤖 AI Analysis")
    
    if st.button("Analyze Ticker") and search_ticker and model:
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        if not row.empty:
             val = row[daily_deliv_col].iloc[0]
             pr = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in row else "N/A"
             
             fund_info = get_fundamentals(search_ticker)
             fund_txt = ""
             if fund_info:
                 fund_txt = (f"Fundamentals: Sales are {fund_info['Sales Trend']}, "
                             f"Margins are {fund_info['OPM Trend']}, "
                             f"EPS is {fund_info['EPS Trend']}.")

             prompt = (
                 f"Act as a stock market expert. Analyze the stock {search_ticker}. "
                 f"Current Price: {pr}. Today's Delivery Percentage: {val}%. "
                 f"{fund_txt} "
                 "Combine Technical (Delivery) and Fundamental (Growth) data. "
                 "Is this a 'Turnaround Story' or 'Strong Compounder'? "
                 "Explain why in 2-3 clear sentences. Do not give financial advice."
             )
             
             with st.spinner("AI thinking..."):
                 st.write(model.generate_content(prompt).text)
        else:
            st.warning("Data not found for AI analysis.")
