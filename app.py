import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market
import google.generativeai as genai

# Setup AI
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Vivek's Alpha Dashboard", layout="wide")
st.title("🇮🇳 Indian Market Accumulation Tracker")

ticker = st.text_input("Enter NSE Ticker (e.g., RELIANCE)", "RELIANCE")

if st.button("Fetch & Analyze Data"):
    data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
    data['DELIV_PER'] = pd.to_numeric(data['DELIV_PER'], errors='coerce')
    latest_deliv = data['DELIV_PER'].iloc[-1]
    
    st.metric(label="Latest Delivery %", value=f"{latest_deliv}%")
    st.dataframe(data.tail(10))

st.divider()
st.subheader("🤖 AI Market Decoder")
analysis_type = st.selectbox("Select Analysis", ["Earnings Call Decoder", "Economic Moat Analysis", "Risk Assessment", "Growth Outlook"])

if st.button("Run AI Analysis"):
    with st.spinner("AI is decoding market data..."):
        prompt = f"Analyze {ticker} stock based on {analysis_type}. Provide a professional summary for an investor."
        response = model.generate_content(prompt)
        st.markdown(response.text)
