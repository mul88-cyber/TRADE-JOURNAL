import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import numpy as np
import pytz
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------------
# KONEKSI KE GOOGLE SHEETS
# -----------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# --- V3.1: Dihapus 'Chart URL'. Total 18 kolom ---
COLUMN_NAMES = [
    "Timestamp", "Pairs", "Direction", "Entry Price", "Stop Loss", 
    "Take Profit", "Exit Price", "Position Size", "PNL (USDT)", "PNL (%)", 
    "RRR", "Leverage", "Timeframe", "Strategy", "Setup Quality", 
    "Emotion Pre-Trade", "Emotion Post-Trade", "Lesson Learned" 
]


@st.cache_resource(ttl=300)
def get_gsheet_client():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=60)
def open_worksheet(_client):
    """
    Membuka GSheet. Argumen '_client' di-cache.
    """
    try:
        spreadsheet = _client.open("Trade Journal")
        worksheet = spreadsheet.sheet1
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("GSheet 'Trade Journal' tidak ditemukan. Pastikan nama file sudah benar dan email bot sudah di-share ke service account.")
        return None
    except Exception as e:
        st.error(f"Error saat membuka GSheet: {e}")
        return None

# --- PERBAIKAN BUG CACHE (v3.0) ---
@st.cache_data(ttl=60)
def get_data_as_dataframe(_worksheet):
    """
    Mengambil data dari worksheet. Argumen '_worksheet' diabaikan oleh cache 
    Streamlit untuk menghindari error 'Cannot hash'.
    """
    try:
        data = _worksheet.get_all_values()
        
        if len(data) <= 1:
            return pd.DataFrame(columns=COLUMN_NAMES) 

        df = pd.DataFrame(data[1:], columns=COLUMN_NAMES)
        
        numeric_cols = ["Entry Price", "Stop Loss", "Take Profit", "Exit Price", 
                        "Position Size", "PNL (USDT)", "Leverage"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%Y-%m-%d %H:%M:%S", errors='coerce')
        df = df.dropna(subset=['Timestamp']) 
        
        return df
    except Exception as e:
        st.error(f"Error saat memproses data GSheet: {e}")
        st.info("Pastikan nama kolom di GSheet SAMA PERSIS dengan list 'COLUMN_NAMES' di kode.")
        return pd.DataFrame()


# -----------------------------------------------------------------
# APLIKASI STREAMLIT
# -----------------------------------------------------------------

st.set_page_config(page_title="Kokpit Trader Pro v3.1", layout="wide")

# --- UPGRADE v3.0: Custom CSS untuk Background (Rekomendasi Nyaman) ---
st.markdown("""
    <style>
    .stApp {
        /* Gradien "Dark Ocean" - Nyaman di mata */
        background: linear-gradient(to right, #0f2027, #203a43, #2c5364);
        color: white; 
    }
    h1, h2, h3, h4, h5, h6, .st-b5, .st-b6, .st-at, .st-au, .st-av, .st-aw, .st-ax, .st-ay, .st-az, .st-b0, .st-b1, .st-b2, .st-b3, .st-b4 {
        color: white !important; 
    }
    .stAlert {
        color: black !important; 
    }
    .css-1d391kg e1fqkh3o1 {
        color: white !important;
    }
    .css-pkzbrp.eqr7zpz4 { 
        color: white !important;
    }
    .stSidebar .stSelectbox > label, 
    .stSidebar .stMultiSelect > label {
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)
# --------------------------------------------------------------

st.title("🚀 Kokpit Trader Pro v3.1 (Plan -> Log -> Review)")
st.markdown("Dibangun untuk *workflow* trading yang disiplin.")

try:
    client = get_gsheet_client()
    worksheet = open_worksheet(client) if client else None

    if worksheet:
        st.success("✅ Berhasil terkoneksi ke Google Sheet 'Trade Journal'!")

        tab_kalkulator, tab_input, tab_dashboard = st.tabs([
            "💰 Kalkulator (Plan)", 
            "✍️ Input Trade (Log)", 
            "📊 Dashboard (Review)"
        ])

        # ----------------------------------------------------
        # TAB 1: KALKULATOR RRR & LIQ. PRICE
        # ----------------------------------------------------
        with tab_kalkulator:
            st.header("Perencana Posisi (RRR & Estimasi Likuidasi)")
            st.markdown("Gunakan ini **SEBELUM** Anda menekan tombol *buy/sell* di *exchange*.")
            
            with st.form(key="calculator_form", clear_on_submit=False):
                col_calc_input_1, col_calc_input_2 = st.columns(2)
                
                with col_calc_input_1:
                    st.subheader("Data Rencana")
                    calc_direction = st.selectbox("Direction*", ["LONG", "SHORT"], key="calc_dir")
                    calc_entry = st.number_input("Entry Price*", value=0.0, help="Harga Anda berencana masuk", format="%.8f")
                    calc_sl = st.number_input("Stop Loss*", value=0.0, help="Harga cut loss Anda", format="%.8f")
                    calc_tp = st.number_input("Take Profit*", value=0.0, help="Harga target profit Anda", format="%.8f")
                
                with col_calc_input_2:
                    st.subheader("Data Margin & Posisi")
                    calc_size_usdt = st.number_input("Position Size (USDT)*", value=0.0, help="Total nilai posisi (Value), BUKAN margin.", format="%.2f")
                    calc_margin_type = st.selectbox("Margin Type*", ["Isolated", "Cross"], help="Pilih mode margin Anda.")
                    
                    if calc_margin_type == 'Isolated':
                        calc_leverage = st.number_input("Leverage (x)*", min_value=1, step=1, value=20, help="Leverage untuk mode Isolated.")
                    else: 
                        calc_equity = st.number_input("Total Equity (Wallet)*", value=0.0, help="Total ekuitas di dompet futures Anda.", format="%.2f")
                
                calculate_button = st.form_submit_button(label="Hitung Risk/Reward & Estimasi Likuidasi")

            if calculate_button:
                st.divider()
                st.subheader("Hasil Perhitungan Rencana:")
                
                valid_prices = all([calc_entry > 0, calc_sl > 0, calc_tp > 0, calc_size_usdt > 0])
                valid_margin = True
                if calc_margin_type == 'Isolated':
                    if calc_leverage <= 0:
                        valid_margin = False
                else: 
                    if calc_equity <= 0:
                        valid_margin = False

                if not valid_prices or not valid_margin:
                    st.error("❌ Semua field (*) wajib diisi dan tidak boleh nol (0).")
                
                elif calc_direction == "LONG" and (calc_entry < calc_sl or calc_entry > calc_tp):
                    st.error("❌ Untuk LONG: SL harus < Entry, dan TP harus > Entry.")
                elif calc_direction == "SHORT" and (calc_entry > calc_sl or calc_entry < calc_tp):
                    st.error("❌ Untuk SHORT: SL harus > Entry, dan TP harus < Entry.")
                else:
                    qty_koin = calc_size_usdt / calc_entry if calc_entry != 0 else 0
                    
                    if calc_direction == "LONG":
                        risk_per_koin = calc_entry - calc_sl
                        reward_per_koin = calc_tp - calc_entry
                    else: 
                        risk_per_koin = calc_sl - calc_entry
                        reward_per_koin = calc_entry - calc_tp
                        
                    risk_dolar = risk_per_koin * qty_koin
                    reward_dolar = reward_per_koin * qty_koin
                    rrr = np.divide(reward_dolar, risk_dolar) if risk_dolar != 0 else 0 
                    
                    liq_price = 0.0
                    if calc_margin_type == 'Isolated':
                        margin_isolated = calc_size_usdt / calc_leverage if calc_leverage != 0 else 0
                        if qty_koin != 0: 
                            if calc_direction == 'LONG':
                                liq_price = calc_entry - (margin_isolated / qty_koin)
                            else: 
                                liq_price = calc_entry + (margin_isolated / qty_koin)
                    else: 
                        if qty_koin != 0: 
                            if calc_direction == 'LONG':
                                liq_price = calc_entry - (calc_equity / qty_koin)
                            else: 
                                liq_price = calc_entry + (calc_equity / qty_koin)
                    
                    st.info(f"**Kuantitas Koin:** `{qty_koin:.8f}` (dihitung dari Size / Entry)")
                    
                    col_risk, col_reward, col_rrr = st.columns(3)
                    col_risk.metric("POTENSI RISK", f"${risk_dolar:,.2f}", "Jika kena SL")
                    col_reward.metric("POTENSI REWARD", f"${reward_dolar:,.2f}", "Jika kena TP")
                    col_rrr.metric("Risk/Reward Ratio (RRR)", f"1 : {rrr:.2f}")
                    
                    st.divider()
                    
                    st.metric(
                        label=f"ESTIMASI LIQ. PRICE ({calc_margin_type})", 
                        value=f"${liq_price:,.8f}"
                    )
                    st.warning("`Perhatian:` Estimasi Liq. Price **TIDAK** termasuk *maintenance margin*, *fees*, atau *funding rates*. Harga likuidasi di exchange mungkin sedikit berbeda.")

                    if rrr < 2.0:
                        st.warning(f"**PERHATIAN:** RRR (1:{rrr:.2f}) di bawah standar profesional (1:2). Trade ini mungkin tidak layak diambil.")
                    else:
                        st.success(f"**GO!** RRR (1:{rrr:.2f}) memenuhi standar. Jika setup Anda valid (A/B), trade ini layak dieksekusi.")


        # ----------------------------------------------------
        # TAB 2: INPUT TRADE
        # ----------------------------------------------------
        with tab_input:
            st.header("Catat Trade Baru")
            st.markdown("Input harga fleksibel. PNL & RRR otomatis.")
            
            with st.form(key="trade_form", clear_on_submit=True):
                col_input_1, col_input_2, col_input_3 = st.columns(3)
                
                with col_input_1:
                    st.subheader("Data Setup")
                    pairs = st.text_input("Pairs*", help="e.g., BTC/USDT")
                    direction = st.selectbox("Direction*", ["LONG", "SHORT"])
                    timeframe = st.selectbox("Timeframe*", ["1m", "5m", "15m", "30m", "1H", "4H", "1D"])
                    strategy = st.text_input("Strategy", help="e.g., Break & Retest")
                
                with col_input_2:
                    st.subheader("Data Rencana (Plan)")
                    entry_price = st.number_input("Entry Price*", value=0.0, help="Harga Anda masuk", format="%.8f")
                    stop_loss = st.number_input("Stop Loss*", value=0.0, help="Harga cut loss", format="%.8f")
                    take_profit = st.number_input("Take Profit*", value=0.0, help="Harga target", format="%.8f")
                    leverage = st.number_input("Leverage (x)*", min_value=1, step=1, value=20)
                    position_size = st.number_input("Position Size (USDT)*", value=0.0, help="Total nilai posisi, BUKAN margin", format="%.2f")

                with col_input_3:
                    st.subheader("Data Hasil & Psikologis")
                    exit_price = st.number_input("Exit Price*", value=0.0, help="Harga Anda keluar. Ini akan menghitung PNL otomatis.", format="%.8f")
                    setup_quality = st.selectbox("Kualitas Setup", ["A (High-Prob)", "B (Good-Prob)", "C (Low-Prob)"])
                    emotion_pre = st.selectbox("Emosi Pre-Trade", ["Confident", "Anxious", "Calm", "FOMO", "Bored"])
                    emotion_post = st.selectbox("Emosi Post-Trade", ["Happy", "Regret", "Angry", "Calm", "Neutral"])

                st.subheader("Review & Pembelajaran")
                # --- V3.1: Input Chart URL dihapus ---
                lesson_learned = st.text_area("Lesson Learned (Apa yang harus dilakukan/dihindari?)")

                submit_button = st.form_submit_button(label="Simpan Trade & Hitung PNL")

                if submit_button:
                    if not all([pairs, entry_price > 0, stop_loss > 0, take_profit > 0, position_size > 0, exit_price > 0]):
                        st.error("❌ Data dengan tanda bintang (*) wajib diisi dan tidak boleh nol (0). Cek kembali input harga & size.")
                    else:
                        with st.spinner("Menghitung PNL & RRR (Zona Waktu WIB)..."):
                            jakarta_tz = pytz.timezone('Asia/Jakarta')
                            timestamp = datetime.now(jakarta_tz).strftime("%Y-%m-%d %H:%M:%S")
                            
                            qty_koin = position_size / entry_price if entry_price != 0 else 0
                            pnl_usdt = (exit_price - entry_price) * qty_koin if direction == "LONG" else (entry_price - exit_price) * qty_koin
                            margin_used = position_size / leverage if leverage != 0 else 0
                            pnl_percent = np.divide(pnl_usdt, margin_used) * 100 if margin_used != 0 else 0
                            
                            risk_per_koin = abs(entry_price - stop_loss)
                            reward_per_koin = abs(take_profit - entry_price)
                            rr_ratio = np.divide(reward_per_koin, risk_per_koin) if risk_per_koin > 0 else 0 

                            # --- V3.1: 'chart_url' dihapus dari baris baru ---
                            new_row = [
                                timestamp, pairs, direction, entry_price, stop_loss,
                                take_profit, exit_price, position_size, round(pnl_usdt, 4),
                                f"{pnl_percent:.2f}%", f"1:{rr_ratio:.2f}", leverage,
                                timeframe, strategy, setup_quality, emotion_pre,
                                emotion_post, lesson_learned 
                            ]
                            
                            worksheet.append_row(new_row)
                            
                            st.success(f"✅ Trade {pairs} ({direction}) berhasil dicatat! (WIB: {timestamp})")
                            if pnl_usdt > 0:
                                st.balloons()
                                st.success(f"Profit: ${pnl_usdt:,.2f} ({pnl_percent:.2f}%)")
                            else:
                                st.warning(f"Loss: ${pnl_usdt:,.2f} ({pnl_percent:.2f}%) - Review pelajarannya!")


        # ----------------------------------------------------
        # TAB 3: DASHBOARD (UI/UX & Fix)
        # ----------------------------------------------------
        with tab_dashboard:
            st.header("Dashboard Performa Trading")
            st.markdown("Review ini setiap akhir pekan. Data adalah guru terbaik.")
            
            with st.spinner("Memuat dan memproses data dari GSheet..."):
                df_raw = get_data_as_dataframe(worksheet)
            
            if df_raw.empty:
                st.warning("Data jurnal masih kosong. Silakan input trade pertama Anda!")
            else:
                # --- Sidebar Filters ---
                st.sidebar.header("📊 Filter Dashboard")
                
                unique_pairs = df_raw["Pairs"].unique()
                selected_pairs = st.sidebar.multiselect("Filter Pairs", unique_pairs, default=unique_pairs)
                
                unique_strategies = df_raw[df_raw["Strategy"] != '']["Strategy"].unique()
                selected_strategies = st.sidebar.multiselect("Filter Strategi", unique_strategies, default=unique_strategies)

                unique_setup_quality = df_raw["Setup Quality"].unique()
                selected_setup_quality = st.sidebar.multiselect("Filter Kualitas Setup", unique_setup_quality, default=unique_setup_quality)

                df = df_raw[
                    (df_raw["Pairs"].isin(selected_pairs)) &
                    (df_raw["Strategy"].isin(unique_strategies if not selected_strategies else selected_strategies)) &
                    (df_raw["Setup Quality"].isin(selected_setup_quality))
                ].copy() 
                
                if df.empty:
                    st.warning("Tidak ada data yang cocok dengan filter Anda.")
                    st.stop() 

                st.subheader("Analisis Cepat Performa (Sesuai Filter)")
                
                total_pnl = df["PNL (USDT)"].sum()
                total_trades = len(df)
                wins = df[df["PNL (USDT)"] > 0]
                losses = df[df["PNL (USDT)"] < 0]
                
                total_wins = len(wins)
                total_losses = len(losses)
                win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
                avg_win = wins["PNL (USDT)"].mean() if total_wins > 0 else 0
                avg_loss = abs(losses["PNL (USDT)"].mean()) if total_losses > 0 else 0
                
                total_profit = wins["PNL (USDT)"].sum()
                total_loss_abs = abs(losses["PNL (USDT)"].sum())
                profit_factor = np.divide(total_profit, total_loss_abs) if total_loss_abs > 0 else 999.0 
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total PNL (USDT)", f"${total_pnl:,.2f}")
                col2.metric("Total Trades", total_trades)
                col3.metric("Win Rate", f"{win_rate:.2f}%")
                
                col4, col5, col6 = st.columns(3)
                col4.metric("Avg. Win ($)", f"${avg_win:,.2f}")
                col5.metric("Avg. Loss ($)", f"${avg_loss:,.2f}")
                col6.metric("Profit Factor", f"{profit_factor:,.2f}", help="Total Profit / Total Loss")

                st.divider()

                st.subheader("Equity Curve (Kumulatif PNL)")
                df_sorted = df.sort_values(by="Timestamp")
                df_sorted['Cumulative PNL'] = df_sorted["PNL (USDT)"].cumsum()
                st.line_chart(df_sorted, y='Cumulative PNL', x='Timestamp', use_container_width=True)
                
                
                st.subheader("Analisis Performa Mendalam")
                
                col_analytic_1, col_analytic_2, col_analytic_3 = st.columns(3)
                
                with col_analytic_1:
                    st.markdown("**PNL Berdasarkan Strategi**")
                    pnl_by_strategy = df[df["Strategy"] != ''].groupby("Strategy")["PNL (USDT)"].sum().sort_values(ascending=False)
                    st.bar_chart(pnl_by_strategy, use_container_width=True)

                with col_analytic_2:
                    st.markdown("**PNL Berdasarkan Kualitas Setup**")
                    pnl_by_setup = df.groupby("Setup Quality")["PNL (USDT)"].sum().sort_values(ascending=False)
                    st.bar_chart(pnl_by_setup, use_container_width=True)

                with col_analytic_3:
                    st.markdown("**PNL Berdasarkan Emosi Pre-Trade**")
                    pnl_by_emotion = df.groupby("Emotion Pre-Trade")["PNL (USDT)"].sum().sort_values(ascending=False)
                    st.bar_chart(pnl_by_emotion, use_container_width=True)
                
                st.markdown("`Insight:` Cek strategi, kualitas setup, dan emosi mana yang paling profit/rugi.")
                st.divider()

                with st.expander("Lihat Semua Catatan Trade (Sesuai Filter)", expanded=False):
                    st.dataframe(df.sort_values(by="Timestamp", ascending=False), use_container_width=True)
                
                st.subheader("Pelajaran Penting (Review)")
                col_lesson_1, col_lesson_2 = st.columns(2)
                
                with col_lesson_1:
                    st.success("Top 3 Wins")
                    top_wins = df.sort_values(by="PNL (USDT)", ascending=False).head(3)
                    for _, row in top_wins.iterrows():
                        st.write(f"**${row['PNL (USDT)']:,.2f}** - {row['Pairs']} ({row['Strategy']})")
                        # --- V3.1: Link Chart URL dihapus ---
                        st.caption(f"Lesson: {row['Lesson Learned']}")
                
                with col_lesson_2:
                    st.error("Top 3 Losses")
                    top_losses = df.sort_values(by="PNL (USDT)", ascending=True).head(3)
                    for _, row in top_losses.iterrows():
                        st.write(f"**${row['PNL (USDT)']:,.2f}** - {row['Pairs']} ({row['Strategy']})")
                        # --- V3.1: Link Chart URL dihapus ---
                        st.caption(f"Lesson: {row['Lesson Learned']}")

except Exception as e:
    if "gcp_service_account" in str(e):
        st.error("Error: 'gcp_service_account' tidak ditemukan di Streamlit Secrets. Pastikan 'secrets.toml' Anda sudah benar.")
    elif "SpreadsheetNotFound" in str(e):
        st.error("Error: GSheet 'Trade Journal' tidak ditemukan. Cek nama file dan pastikan email bot sudah di-share.")
    # --- V3.1: Error message di-update jadi 18 kolom ---
    elif "Mismatched" in str(e) or "column count" in str(e):
        st.error("Error: Jumlah kolom GSheet (harus 18) tidak cocok dengan kode. Pastikan urutan di GSheet SAMA PERSIS dengan 'COLUMN_NAMES'.")
        st.error("Urutan yang Benar: Timestamp, Pairs, Direction, Entry Price, Stop Loss, Take Profit, Exit Price, Position Size, PNL (USDT), PNL (%), RRR, Leverage, Timeframe, Strategy, Setup Quality, Emotion Pre-Trade, Emotion Post-Trade, Lesson Learned")
    else:
        st.error(f"Terjadi Error. Cek koneksi atau detail GSheet Anda.")
        st.error(f"Error detail: {e}")
