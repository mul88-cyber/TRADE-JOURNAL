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

def get_gsheet_client():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

def open_worksheet(client):
    try:
        spreadsheet = client.open("Trade Journal")
        worksheet = spreadsheet.sheet1
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("GSheet 'Trade Journal' tidak ditemukan. Pastikan nama file sudah benar dan email bot sudah di-share ke service account.")
        return None
    except Exception as e:
        st.error(f"Error saat membuka GSheet: {e}")
        return None

# -----------------------------------------------------------------
# APLIKASI STREAMLIT
# -----------------------------------------------------------------

st.set_page_config(page_title="Kokpit Trader Pro v2.8", layout="wide")
st.title("🚀 Kokpit Trader Pro v2.8 (Plan -> Log -> Review)")
st.markdown("Dibangun untuk *workflow* trading yang disiplin.")

try:
    # Koneksi ke GSheet
    client = get_gsheet_client()
    worksheet = open_worksheet(client) if client else None

    if worksheet:
        st.success("✅ Berhasil terkoneksi ke Google Sheet 'Trade Journal'!")

        # --- TABS NAVIGASI (v2.8) ---
        tab_kalkulator, tab_input, tab_dashboard = st.tabs([
            "💰 Kalkulator (Plan)", 
            "✍️ Input Trade (Log)", 
            "📊 Dashboard (Review)"
        ])

        # ----------------------------------------------------
        # TAB 1: KALKULATOR RRR & LIQ. PRICE (v2.8)
        # ----------------------------------------------------
        with tab_kalkulator:
            st.header("Perencana Posisi (RRR & Estimasi Likuidasi)")
            st.markdown("Gunakan ini **SEBELUM** Anda menekan tombol *buy/sell* di *exchange*.")
            
            with st.form(key="calculator_form", clear_on_submit=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Data Rencana")
                    calc_direction = st.selectbox("Direction*", ["LONG", "SHORT"], key="calc_dir")
                    calc_entry = st.number_input("Entry Price*", value=0.0, help="Harga Anda berencana masuk")
                    calc_sl = st.number_input("Stop Loss*", value=0.0, help="Harga cut loss Anda")
                    calc_tp = st.number_input("Take Profit*", value=0.0, help="Harga target profit Anda")
                
                with col2:
                    st.subheader("Data Margin & Posisi")
                    calc_size_usdt = st.number_input("Position Size (USDT)*", value=0.0, help="Total nilai posisi (Value), BUKAN margin.")
                    calc_margin_type = st.selectbox("Margin Type*", ["Isolated", "Cross"], help="Pilih mode margin Anda.")
                    
                    # Input dinamis berdasarkan Margin Type
                    if calc_margin_type == 'Isolated':
                        calc_leverage = st.number_input("Leverage (x)*", min_value=1, step=1, value=20, help="Leverage untuk mode Isolated.")
                    else: # Cross
                        calc_equity = st.number_input("Total Equity (Wallet)*", value=0.0, help="Total ekuitas di dompet futures Anda.")
                
                calculate_button = st.form_submit_button(label="Hitung Risk/Reward & Estimasi Likuidasi")

            # --- Area Output Kalkulator ---
            if calculate_button:
                st.divider()
                st.subheader("Hasil Perhitungan Rencana:")
                
                # Validasi input
                valid_prices = all([calc_entry > 0, calc_sl > 0, calc_tp > 0, calc_size_usdt > 0])
                valid_margin = True
                if calc_margin_type == 'Isolated':
                    if calc_leverage <= 0:
                        valid_margin = False
                else: # Cross
                    if calc_equity <= 0:
                        valid_margin = False

                if not valid_prices or not valid_margin:
                    st.error("❌ Semua field (*) wajib diisi dan tidak boleh nol (0).")
                
                elif calc_direction == "LONG" and (calc_entry < calc_sl or calc_entry > calc_tp):
                    st.error("❌ Untuk LONG: SL harus < Entry, dan TP harus > Entry.")
                elif calc_direction == "SHORT" and (calc_entry > calc_sl or calc_entry < calc_tp):
                    st.error("❌ Untuk SHORT: SL harus > Entry, dan TP harus < Entry.")
                else:
                    # --- Logika Kalkulasi ---
                    qty_koin = calc_size_usdt / calc_entry
                    
                    if calc_direction == "LONG":
                        risk_per_koin = calc_entry - calc_sl
                        reward_per_koin = calc_tp - calc_entry
                    else: # SHORT
                        risk_per_koin = calc_sl - calc_entry
                        reward_per_koin = calc_entry - calc_tp
                        
                    risk_dolar = risk_per_koin * qty_koin
                    reward_dolar = reward_per_koin * qty_koin
                    rrr = np.divide(reward_dolar, risk_dolar)
                    
                    # --- Logika Liq. Price ---
                    liq_price = 0.0
                    if calc_margin_type == 'Isolated':
                        margin_isolated = calc_size_usdt / calc_leverage
                        if calc_direction == 'LONG':
                            # Harga turun sebanyak (Margin / Qty)
                            liq_price = calc_entry - (margin_isolated / qty_koin)
                        else: # SHORT
                            # Harga naik sebanyak (Margin / Qty)
                            liq_price = calc_entry + (margin_isolated / qty_koin)
                    
                    else: # Cross
                        if calc_direction == 'LONG':
                            # Harga turun sebanyak (Total Equity / Qty)
                            liq_price = calc_entry - (calc_equity / qty_koin)
                        else: # SHORT
                            # Harga naik sebanyak (Total Equity / Qty)
                            liq_price = calc_entry + (calc_equity / qty_koin)
                    
                    # --- Tampilkan Hasil ---
                    st.info(f"**Kuantitas Koin:** `{qty_koin:.8f}` (dihitung dari Size / Entry)")
                    
                    col_risk, col_reward, col_rrr = st.columns(3)
                    col_risk.metric("POTENSI RISK", f"${risk_dolar:,.2f}", "Jika kena SL")
                    col_reward.metric("POTENSI REWARD", f"${reward_dolar:,.2f}", "Jika kena TP")
                    col_rrr.metric("Risk/Reward Ratio (RRR)", f"1 : {rrr:.2f}")
                    
                    st.divider()
                    
                    # Tampilkan Liq. Price
                    st.metric(
                        label=f"ESTIMASI LIQ. PRICE ({calc_margin_type})", 
                        value=f"${liq_price:,.2f}"
                    )
                    st.warning("`Perhatian:` Estimasi Liq. Price **TIDAK** termasuk *maintenance margin*, *fees*, atau *funding rates*. Harga likuidasi di exchange mungkin sedikit berbeda.")

                    if rrr < 2.0:
                        st.warning(f"**PERHATIAN:** RRR (1:{rrr:.2f}) di bawah standar profesional (1:2). Trade ini mungkin tidak layak diambil.")
                    else:
                        st.success(f"**GO!** RRR (1:{rrr:.2f}) memenuhi standar. Jika setup Anda valid (A/B), trade ini layak dieksekusi.")


        # ----------------------------------------------------
        # TAB 2: INPUT TRADE (KODE v2.5 ANDA)
        # ----------------------------------------------------
        with tab_input:
            st.header("Catat Trade Baru")
            st.markdown("Input harga fleksibel (bisa 65000 atau 0.000015). PNL & RRR otomatis.")
            
            with st.form(key="trade_form", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.subheader("Data Setup")
                    pairs = st.text_input("Pairs*", help="e.g., BTC/USDT")
                    direction = st.selectbox("Direction*", ["LONG", "SHORT"])
                    timeframe = st.selectbox("Timeframe*", ["1m", "5m", "15m", "30m", "1H", "4H", "1D"])
                    strategy = st.text_input("Strategy", help="e.g., Break & Retest")
                
                with col2:
                    st.subheader("Data Rencana (Plan)")
                    entry_price = st.number_input("Entry Price*", value=0.0, help="Harga Anda masuk")
                    stop_loss = st.number_input("Stop Loss*", value=0.0, help="Harga cut loss")
                    take_profit = st.number_input("Take Profit*", value=0.0, help="Harga target")
                    leverage = st.number_input("Leverage (x)*", min_value=1, step=1, value=20)
                    position_size = st.number_input("Position Size (USDT)*", value=0.0, help="Total nilai posisi, BUKAN margin")

                with col3:
                    st.subheader("Data Hasil & Psikologis")
                    exit_price = st.number_input("Exit Price*", value=0.0, help="Harga Anda keluar. Ini akan menghitung PNL otomatis.")
                    setup_quality = st.selectbox("Kualitas Setup", ["A (High-Prob)", "B (Good-Prob)", "C (Low-Prob)"])
                    emotion_pre = st.selectbox("Emosi Pre-Trade", ["Confident", "Anxious", "Calm", "FOMO", "Bored"])
                    emotion_post = st.selectbox("Emosi Post-Trade", ["Happy", "Regret", "Angry", "Calm", "Neutral"])

                st.subheader("Review & Pembelajaran")
                lesson_learned = st.text_area("Lesson Learned (Apa yang harus dilakukan/dihindari?)")

                submit_button = st.form_submit_button(label="Simpan Trade & Hitung PNL")

                if submit_button:
                    if not all([pairs, entry_price > 0, stop_loss > 0, take_profit > 0, position_size > 0, exit_price > 0]):
                        st.error("❌ Data dengan tanda bintang (*) wajib diisi dan tidak boleh nol (0). Cek kembali input harga & size.")
                    else:
                        with st.spinner("Menghitung PNL & RRR (Zona Waktu WIB)..."):
                            jakarta_tz = pytz.timezone('Asia/Jakarta')
                            timestamp = datetime.now(jakarta_tz).strftime("%Y-%m-%d %H:%M:%S")
                            
                            qty_koin = position_size / entry_price
                            pnl_usdt = (exit_price - entry_price) * qty_koin if direction == "LONG" else (entry_price - exit_price) * qty_koin
                            margin_used = position_size / leverage
                            pnl_percent = np.divide(pnl_usdt, margin_used) * 100
                            
                            risk_per_koin = abs(entry_price - stop_loss)
                            reward_per_koin = abs(take_profit - entry_price)
                            rr_ratio = np.divide(reward_per_koin, risk_per_koin)

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
        # TAB 3: DASHBOARD (KODE v2.5 ANDA + BUG FIX)
        # ----------------------------------------------------
        with tab_dashboard:
            st.header("Dashboard Performa Trading")
            st.markdown("Review ini setiap akhir pekan. Data adalah guru terbaik.")
            
            with st.spinner("Memuat data dari GSheet..."):
                data = worksheet.get_all_records()
                
            if not data:
                st.warning("Data jurnal masih kosong. Silakan input trade pertama Anda!")
            else:
                df = pd.DataFrame(data)
                
                # --- Data Cleaning ---
                # !!! BUG FIX v2.8: Mengganti PNL_(USNT) -> PNL_(USDT) !!!
                df["PNL_(USDT)"] = pd.to_numeric(df["PNL_(USDT)"], errors='coerce').fillna(0) 
                df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%Y-%m-%d %H:%M:%S", errors='coerce')
                df = df.dropna(subset=['Timestamp'])
                
                # --- Tampilan Dashboard ---
                st.subheader("Semua Catatan Trade (20 Terakhir)")
                st.dataframe(df.sort_values(by="Timestamp", ascending=False).head(20))
                
                st.divider()
                st.subheader("Analisis Cepat Performa")
                
                total_pnl = df["PNL_(USDT)"].sum()
                total_trades = len(df)
                wins = df[df["PNL_(USDT)"] > 0]
                losses = df[df["PNL_(USDT)"] < 0]
                
                total_wins = len(wins)
                total_losses = len(losses)
                win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
                avg_win = wins["PNL_(USDT)"].mean() if total_wins > 0 else 0
                avg_loss = abs(losses["PNL_(USDT)"].mean()) if total_losses > 0 else 0
                
                # Perbaikan kecil untuk profit factor jika tidak ada loss
                total_profit = wins["PNL_(USDT)"].sum()
                total_loss_abs = abs(losses["PNL_(USDT)"].sum())
                profit_factor = np.divide(total_profit, total_loss_abs) if total_loss_abs > 0 else 999.0 # Anggap 999 jika tdk ada loss
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total PNL (USDT)", f"${total_pnl:,.2f}")
                col2.metric("Total Trades", total_trades)
                col3.metric("Win Rate", f"{win_rate:.2f}%")
                
                col4, col5, col6 = st.columns(3)
                col4.metric("Avg. Win ($)", f"${avg_win:,.2f}")
                col5.metric("Avg. Loss ($)", f"${avg_loss:,.2f}")
                col6.metric("Profit Factor", f"{profit_factor:,.2f}", help="Total Profit / Total Loss")

                st.subheader("Equity Curve (Kumulatif PNL)")
                df_sorted = df.sort_values(by="Timestamp")
                df_sorted['Cumulative PNL'] = df_sorted["PNL_(USDT)"].cumsum()
                st.line_chart(df_sorted, y='Cumulative PNL', x='Timestamp')
                
                st.subheader("Analisis PNL berdasarkan Emosi Pre-Trade")
                pnl_by_emotion = df.groupby("Emotion_pre_trade_Confident/Anxious/Calm")["PNL_(USDT)"].sum()
                st.bar_chart(pnl_by_emotion)
                st.markdown("`Insight:` Cek emosi mana yang paling sering menghasilkan *loss*.")

except Exception as e:
    if "gcp_service_account" in str(e):
         st.error("Error: 'gcp_service_account' tidak ditemukan di Streamlit Secrets. Pastikan 'secrets.toml' Anda sudah benar.")
    elif "SpreadsheetNotFound" in str(e):
        st.error("Error: GSheet 'Trade Journal' tidak ditemukan. Cek nama file dan pastikan email bot sudah di-share.")
    elif "Mismatched" in str(e) or "column count" in str(e):
         st.error("Error: Jumlah kolom GSheet (18) tidak cocok dengan kode. Pastikan urutan di GSheet SAMA PERSIS dengan di `new_row`.")
    else:
        st.error(f"Terjadi Error. Cek koneksi atau detail GSheet Anda.")
        st.error(f"Error detail: {e}")
