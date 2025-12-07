import streamlit as st
import pandas as pd
import glob
import os
import time
import numpy as np
import altair as alt

# --- CONFIGURATION ---
st.set_page_config(page_title="Whoop OS v4", page_icon="🔋", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #000000; color: #e0e0e0; }
    .metric-box {
        background-color: #111; border: 1px solid #333;
        border-radius: 10px; padding: 15px; text-align: center;
    }
    .big-num { font-size: 3rem; font-weight: 800; }
    .label { font-size: 0.9rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    /* Style batterie */
    .batt-box {
        border: 2px solid #555; border-radius: 5px; padding: 5px; 
        text-align: center; font-weight: bold; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS ---
def get_latest_csv():
    files = glob.glob('data/session_*.csv')
    if not files: return None
    return max(files, key=os.path.getctime)

def parse_rr(rr_str):
    if pd.isna(rr_str) or rr_str == "": return []
    try: return [int(x) for x in str(rr_str).split(';') if x.strip() and 250 < int(x) < 1500]
    except: return []

def calc_rmssd(rr_list):
    if len(rr_list) < 2: return 0
    diffs = np.diff(rr_list)
    return np.sqrt(np.mean(diffs ** 2))

# --- LOGIQUE ---
csv_file = get_latest_csv()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Whoop_Inc._Logo.jpg/640px-Whoop_Inc._Logo.jpg", width=150)
    
    # Placeholder pour la batterie (on le remplit après lecture du CSV)
    batt_placeholder = st.empty()
    
    st.header("⚙️ Réglages")
    MAX_HR = st.number_input("Freq. Cardiaque Max", value=190, step=1)
    sleep_mode = st.toggle("🌙 Mode Sommeil", value=False)
    
    if st.button("🔄 Rafraîchir"): st.rerun()

if not csv_file:
    st.info("📡 En attente du Logger V4...")
    time.sleep(2)
    st.rerun()

try:
    # Lecture avec 4 colonnes maintenant
    # On utilise 'usecols' pour être sûr, ou on nomme les 4
    try:
        df = pd.read_csv(csv_file, names=["Timestamp", "BPM", "RR", "Battery"], header=0)
    except:
        # Fallback si ancien fichier CSV V3 (3 colonnes)
        df = pd.read_csv(csv_file, names=["Timestamp", "BPM", "RR"], header=0)
        df['Battery'] = 0 # Valeur par défaut
        
    if df.empty: raise ValueError("Empty")
    
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df[df['BPM'] > 0] 
    
    # Données Temps Réel
    last_bpm = df['BPM'].iloc[-1]
    last_batt = int(df['Battery'].iloc[-1]) if 'Battery' in df.columns else 0

    # --- MISE A JOUR BATTERIE SIDEBAR ---
    batt_color = "#34c759" # Vert
    if last_batt < 20: batt_color = "#ff3b30" # Rouge
    elif last_batt < 50: batt_color = "#ff9500" # Orange
    
    batt_placeholder.markdown(f"""
        <div class="batt-box" style="border-color: {batt_color}; color: {batt_color};">
            🔋 BATTERIE : {last_batt}%
        </div>
    """, unsafe_allow_html=True)

    # Calculs VFC / Strain
    all_rr = []
    for r in df['RR'].apply(parse_rr): all_rr.extend(r)
    current_hrv = calc_rmssd(all_rr[-50:]) if len(all_rr) > 50 else 0 
    
    df['Strain_Val'] = pd.cut(df['BPM'], 
        bins=[0, MAX_HR*0.5, MAX_HR*0.6, MAX_HR*0.7, MAX_HR*0.8, MAX_HR*0.9, 300], 
        labels=[0, 1, 2, 4, 8, 12], include_lowest=True).astype(float)
    total_strain = df['Strain_Val'].sum()
    strain_score = min(21 * (1 - np.exp(-total_strain / 6000)), 21.0)

    # --- INTERFACE ---
    if sleep_mode:
        st.markdown("<br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            st.markdown(f"""
            <div style='text-align:center; color: #444;'>
                <h2>🌙 MODE NUIT</h2>
                <div style='font-size: 8rem; font-weight: bold; color: #333;'>{last_bpm}</div>
                <div style='font-size: 2rem; color: #34c759;'>VFC: {int(current_hrv)} ms</div>
                <br><div style='color:{batt_color}'>🔋 Batterie: {last_batt}%</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"<div class='metric-box'><div class='big-num' style='color:#fff'>{last_bpm}</div><div class='label'>BPM</div></div>", unsafe_allow_html=True)
        
        s_col = "#34c759" if strain_score < 10 else "#ff3b30"
        c2.markdown(f"<div class='metric-box'><div class='big-num' style='color:{s_col}'>{strain_score:.1f}</div><div class='label'>STRAIN</div></div>", unsafe_allow_html=True)
        
        c3.markdown(f"<div class='metric-box'><div class='big-num' style='color:#34c759'>{int(current_hrv)}</div><div class='label'>VFC (ms)</div></div>", unsafe_allow_html=True)
        
        dur = str(df['Timestamp'].max() - df['Timestamp'].min()).split('.')[0]
        c4.markdown(f"<div class='metric-box'><div class='big-num' style='color:#888'>{dur}</div><div class='label'>DURÉE</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Graphiques
        col_g1, col_g2 = st.columns([2, 1])
        with col_g1:
            st.subheader("📈 Performance")
            chart_data = df.tail(300)
            chart = alt.Chart(chart_data).mark_area(
                line={'color':'#ff3b30'},
                color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#ff3b30', offset=0), alt.GradientStop(color='transparent', offset=1)], x1=1, x2=1, y1=1, y2=0)
            ).encode(x=alt.X('Timestamp', axis=alt.Axis(format='%H:%M:%S')), y=alt.Y('BPM', scale=alt.Scale(domain=[40, MAX_HR])), tooltip=['Timestamp', 'BPM', 'Battery'])
            st.altair_chart(chart, use_container_width=True)

        with col_g2:
            st.subheader("📊 Zones")
            bins = [0, MAX_HR*0.5, MAX_HR*0.6, MAX_HR*0.7, MAX_HR*0.8, MAX_HR*0.9, 300]
            labels = ['Repos', 'Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5']
            df['Zone'] = pd.cut(df['BPM'], bins=bins, labels=labels)
            zone_counts = df['Zone'].value_counts().reset_index()
            zone_counts.columns = ['Zone', 'Count']
            bar = alt.Chart(zone_counts).mark_bar().encode(
                x='Count', y=alt.Y('Zone', sort=labels), 
                color=alt.Color('Zone', scale=alt.Scale(range=['#444', '#888', '#3b82f6', '#10b981', '#f59e0b', '#ef4444']))
            )
            st.altair_chart(bar, use_container_width=True)

except Exception: pass
time.sleep(1)
st.rerun()