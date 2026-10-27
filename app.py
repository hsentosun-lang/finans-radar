import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import os

st.set_page_config(page_title="Kantitatif Hisse Radarı", layout="wide")
DATABASE_URL = os.environ.get("DATABASE_URL", st.secrets.get("DATABASE_URL", ""))

@st.cache_data(ttl=600)
def load_data():
    engine = create_engine(DATABASE_URL)
    df = pd.read_sql_table('market_data', engine)
    df['date'] = pd.to_datetime(df['date'])
    return df

st.title("🎯 Kantitatif Hisse & Ekstrem Durum Radarı")

try: df = load_data()
except Exception: st.error("Veritabanına bağlanılamadı. Lütfen bekleyin veya botu çalıştırın."); st.stop()

son_gun = df['date'].max()
guncel_df = df[df['date'] == son_gun].copy()

st.markdown(f"### 🚨 Ekstrem Durum Radar Paneli ({son_gun.strftime('%d.%m.%Y')})")
def skor_renk(skor):
    if skor >= 70: return 'background-color: #ff4b4b; color: white;'
    elif skor >= 40: return 'background-color: #ffa500; color: black;'
    return 'background-color: #2e7d32; color: white;'

gosterim_ekstrem = guncel_df[['index_name', 'ticker', 'ekstrem_skor', 'z_score_daily', 'percentile_rank', 'atr_ratio']].sort_values('ekstrem_skor', ascending=False)
gosterim_ekstrem.columns = ['Endeks', 'Enstrüman', 'Ekstrem Skoru (0-100)', 'Günlük Z-Skoru', 'Yüzdelik Dilim (%)', 'ATR Oranı']
radar_df = gosterim_ekstrem[gosterim_ekstrem['Ekstrem Skoru (0-100)'] >= 40]

if not radar_df.empty:
    st.dataframe(radar_df.style.map(skor_renk, subset=['Ekstrem Skoru (0-100)']).format({'Günlük Z-Skoru': '{:.2f}', 'Yüzdelik Dilim (%)': '{:.1f}', 'ATR Oranı': '{:.2f}'}), use_container_width=True, hide_index=True)
else: st.success("Tüm varlıklar olağan akışında (0-40 Skoru). Piyasada anomali yok.")
st.markdown("---")

st.sidebar.header("1. Kapsam")
selected_index = st.sidebar.selectbox("Endeks Seçin", df['index_name'].unique().tolist())
tickers_in_index = df[df['index_name'] == selected_index]['ticker'].unique().tolist()
selected_tickers = st.sidebar.multiselect("Hisseler", tickers_in_index, default=tickers_in_index)

st.sidebar.markdown("---")
st.sidebar.header("2. Trend Filtreleri")
if st.sidebar.checkbox("Golden Cross (50 SMA > 200 SMA)"):
    df = df[df['sma_50'] > df['sma_200']]
if st.sidebar.checkbox("Hacim > 2 Sigma"):
    df = df[df['volume'] > df['vol_sigma_2']]

filtered_df = df[df['ticker'].isin(selected_tickers)].copy()

st.subheader("Bireysel Enstrüman Grafiği")
if not filtered_df.empty:
    target = selected_tickers[0] if selected_tickers else None
    if target:
        chart_df = df[df['ticker'] == target].sort_values('date').tail(150)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df['date'], y=chart_df['close'], name='Kapanış', line=dict(color='white')))
        fig.add_trace(go.Scatter(x=chart_df['date'], y=chart_df['sma_50'], name='50 SMA', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=chart_df['date'], y=chart_df['sma_200'], name='200 SMA', line=dict(color='orange')))
        fig.update_layout(title=f"{target} Fiyat (Son 150 Gün)", template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)