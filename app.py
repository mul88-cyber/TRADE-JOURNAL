import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# Page config
st.set_page_config(
    page_title="Trading Journal Pro",
    page_icon="📈",
    layout="wide"
)

# GSHEET Setup
@st.cache_resource
def setup_gsheet():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(st.secrets["1l808C4D-jUCxZTjLsbs4QrjLrwzLeTVtQ5cT1hzrzuk"]).sheet1
    return sheet

def get_current_price(symbol):
    """Get current price from Bybit API"""
    try:
        url = f"https://api.bybit.com/v2/public/tickers?symbol={symbol}"
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['ret_code'] == 0:
            return float(data['result'][0]['last_price'])
    except:
        return None

def calculate_pnl(row, current_prices):
    """Calculate real-time PnL"""
    if pd.isna(row['exit_price']):
        current_price = current_prices.get(row['pair'])
        if current_price:
            if row['direction'] == 'LONG':
                pnl = (current_price - row['entry_price']) * row['position_size']
            else:  # SHORT
                pnl = (row['entry_price'] - current_price) * row['position_size']
            return pnl
    return row['pnl']

# Main App
st.title("📈 Trading Journal Pro")
st.markdown("---")

# Initialize sheet
try:
    sheet = setup_gsheet()
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    
    if not df.empty:
        # Convert numeric columns
        numeric_cols = ['entry_price', 'stop_loss', 'take_profit', 'exit_price', 
                       'position_size', 'pnl', 'pnl_percent', 'risk_reward_ratio', 'leverage']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Convert timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Get current prices for PnL calculation
        current_prices = {}
        unique_pairs = df['pair'].unique()
        for pair in unique_pairs:
            current_prices[pair] = get_current_price(pair)
        
        # Calculate real-time PnL
        df['current_pnl'] = df.apply(calculate_pnl, axis=1, args=(current_prices,))
        
except Exception as e:
    st.error(f"Error loading data: {e}")
    df = pd.DataFrame()

# Sidebar - New Trade Entry
st.sidebar.header("➕ New Trade Entry")

with st.sidebar.form("trade_entry"):
    timestamp = st.date_input("Trade Date", datetime.now())
    pair = st.selectbox("Pair", ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"])
    direction = st.radio("Direction", ["LONG", "SHORT"])
    
    col1, col2 = st.columns(2)
    with col1:
        entry_price = st.number_input("Entry Price", min_value=0.0, format="%.4f")
        position_size = st.number_input("Position Size (USDT)", min_value=0.0)
        leverage = st.number_input("Leverage", min_value=1, value=3)
    with col2:
        stop_loss = st.number_input("Stop Loss", min_value=0.0, format="%.4f")
        take_profit = st.number_input("Take Profit", min_value=0.0, format="%.4f")
    
    emotion_pre = st.selectbox("Pre-Trade Emotion", ["Confident", "Calm", "Anxious", "Greedy", "Fearful"])
    setup_quality = st.selectbox("Setup Quality", ["A", "B", "C"])
    
    notes = st.text_area("Trade Notes / Setup Description")
    
    if st.form_submit_button("💾 Save Trade"):
        new_trade = {
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'pair': pair,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_size': position_size,
            'leverage': leverage,
            'setup_quality': setup_quality,
            'emotion_pre_trade': emotion_pre,
            'lesson_learned': notes,
            'exit_price': '',
            'pnl': '',
            'pnl_percent': '',
            'risk_reward_ratio': abs(take_profit - entry_price) / abs(entry_price - stop_loss) if stop_loss else 0,
            'emotion_post_trade': '',
            'strategy': '',
            'timeframe': '',
            'tags': ''
        }
        
        try:
            sheet.append_row(list(new_trade.values()))
            st.sidebar.success("Trade saved successfully! 🎯")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error saving trade: {e}")

# Main Dashboard
if not df.empty:
    # Real-time PnL Overview
    st.header("📊 Live Portfolio Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_trades = len(df)
    winning_trades = len(df[df['pnl'] > 0]) if 'pnl' in df.columns else 0
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Calculate real-time metrics
    closed_trades = df[df['exit_price'].notna()]
    open_trades = df[df['exit_price'].isna()]
    
    total_pnl = closed_trades['pnl'].sum() if 'pnl' in closed_trades.columns else 0
    open_pnl = open_trades['current_pnl'].sum() if 'current_pnl' in open_trades.columns else 0
    
    with col1:
        st.metric("Total Trades", total_trades)
    with col2:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with col3:
        st.metric("Closed PnL", f"${total_pnl:+.2f}")
    with col4:
        st.metric("Open PnL", f"${open_pnl:+.2f}", delta=f"{open_pnl:+.2f}")

    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # PnL Over Time
        st.subheader("Equity Curve")
        if not closed_trades.empty:
            closed_trades_sorted = closed_trades.sort_values('timestamp')
            closed_trades_sorted['cumulative_pnl'] = closed_trades_sorted['pnl'].cumsum()
            
            fig = px.line(closed_trades_sorted, x='timestamp', y='cumulative_pnl',
                         title="Cumulative PnL Over Time")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Setup Quality Analysis
        st.subheader("Setup Quality Performance")
        if 'setup_quality' in df.columns and 'pnl' in df.columns:
            quality_pnl = df.groupby('setup_quality')['pnl'].mean()
            fig = px.bar(x=quality_pnl.index, y=quality_pnl.values,
                        title="Average PnL by Setup Quality")
            st.plotly_chart(fig, use_container_width=True)

    # Trade History
    st.header("📋 Trade History")
    
    # Show open trades first
    if not open_trades.empty:
        st.subheader("🟡 Open Trades")
        open_display = open_trades[['timestamp', 'pair', 'direction', 'entry_price', 
                                  'stop_loss', 'take_profit', 'position_size', 'current_pnl']]
        open_display['current_pnl'] = open_display['current_pnl'].round(2)
        st.dataframe(open_display, use_container_width=True)
    
    # Show closed trades
    if not closed_trades.empty:
        st.subheader("🟢 Closed Trades")
        closed_display = closed_trades[['timestamp', 'pair', 'direction', 'entry_price',
                                      'exit_price', 'position_size', 'pnl', 'pnl_percent']]
        st.dataframe(closed_display, use_container_width=True)

else:
    st.info("No trades recorded yet. Start by adding your first trade in the sidebar! 🚀")

# Footer
st.markdown("---")
st.markdown("**Trading Journal Pro** - Built for disciplined traders 🎯")
