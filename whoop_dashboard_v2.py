import streamlit as st
import pandas as pd
import glob
import os
import time
import numpy as np
import altair as alt

# ==========================================
# CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Whoop Clone V2",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Thème sombre style "Hacker / Whoop"
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    .metric-card {
        background-color: #1f2937;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #374151;
        text-align: center;
    }
    h1, h2, h3 { color: #ffffff; }
    .big-stat { font-size: 2.5rem; font-weight: bold; color: #ff3b30; }
    .hrv-stat { font-size: 2.5rem; font-weight: bold; color: #34c759; }
</style>
""", unsafe_allow_html=True)

MAX_HR = 190  # Votre fréquence max estimée

# ==========================================
# FONCTIONS MÉTIER
# ==========================================

def get_latest_csv():
    """Trouve le fichier CSV le plus récent."""
    list_of_files = glob.glob('whoop_session_*.csv') 
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getctime)

def parse_rr_intervals(rr_str):
    """Convertit la chaine '800;810' en liste [800, 810]."""
    if pd.isna(rr_str) or rr_str == "":
        return []
    try:
        # On filtre les valeurs absurdes (> 1300ms = < 46 bpm, < 300ms = > 200 bpm) pour éviter le bruit
        values = [int(x) for x in str(rr_str).split(';') if x.strip()]
        return [v for v in values if 300 < v < 1500]
    except:
        return []

def calculate_rmssd(rr_list):
    """Calcul du RMSSD (Standard Or pour la VFC/Recovery)."""
    if len(rr_list) < 2:
        return 0
    diffs = np.diff(rr_list)
    squared_diffs = diffs ** 2
    mean_squared = np.mean(squared_diffs)
    return np.sqrt(mean_squared)

def calculate_strain_and_zones(df):
    """Calcul des zones cardiaques et du score d'effort."""
    # Définition des zones
    conditions = [
        (df['BPM'] < MAX_HR * 0.5),
        (df['BPM'] >= MAX_HR * 0.5) & (df['BPM'] < MAX_HR * 0.6),
        (df['BPM'] >= MAX_HR * 0.6) & (df['BPM'] < MAX_HR * 0.7),
        (df['BPM'] >= MAX_HR * 0.7) & (df['BPM'] < MAX_HR * 0.8),
        (df['BPM'] >= MAX_HR * 0.8) & (df['BPM'] < MAX_HR * 0.9),
        (df['BPM'] >= MAX_HR * 0.9)
    ]
    choices = ['Repos', 'Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5']
    df['Zone'] = np.select(conditions, choices, default='Repos')

    # Calcul Strain (somme pondérée simplifiée)
    # On suppose 1 point de donnée = ~1 seconde (pour simplifier le live)
    strain_weights = {'Repos': 0, 'Zone 1': 1, 'Zone 2': 2, 'Zone 3': 4, 'Zone 4': 8, 'Zone 5': 12}
    df['Strain_Points'] = df['Zone'].map(strain_weights)
    total_strain_raw = df['Strain_Points'].sum()
    
    # Formule logarithmique pseudo-Whoop (0-21)
    # Un vrai workout dur fait ~5000-10000 points bruts avec cette échelle
    if total_strain_raw == 0:
        strain_score = 0
    else:
        strain_score = 21 * (1 - np.exp(-total_strain_raw / 5000))
    
    return df, min(strain_score, 21.0)

# ==========================================
# INTERFACE
# ==========================================

st.title("🧬 Whoop Clone : Ultimate Monitor")

csv_file = get_latest_csv()

if not csv_file:
    st.warning("⚠️ En attente du Logger V2...")
    time.sleep(2)
    st.rerun()

try:
    # Lecture du CSV avec gestion de la nouvelle colonne
    df = pd.read_csv(csv_file, names=["Timestamp", "BPM", "RR_String"], header=0)
    
    # Si le fichier vient juste d'être créé et est vide
    if df.empty:
        time.sleep(1)
        st.rerun()

    # Nettoyage et typage
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df[df['BPM'] > 0] # Filtre les 0 parasites

    # --- CALCULS VFC (HRV) ---
    # On extrait tous les intervalles RR de la session
    all_rr = []
    df['RR_List'] = df['RR_String'].apply(parse_rr_intervals)
    for rrs in df['RR_List']:
        all_rr.extend(rrs)
    
    # Calcul du RMSSD global (Session HRV)
    session_hrv = calculate_rmssd(all_rr)
    
    # Calcul du RMSSD Instantané (sur les 60 dernières secondes seulement)
    # Pour voir le stress en direct
    recent_rr = []
    if len(df) > 60:
        recent_df = df.tail(60)
        for rrs in recent_df['RR_List']:
            recent_rr.extend(rrs)
    else:
        recent_rr = all_rr
    
    instant_hrv = calculate_rmssd(recent_rr)

    # --- CALCULS STRAIN ---
    df, strain_score = calculate_strain_and_zones(df)

    # --- AFFICHAGE DASHBOARD ---
    
    # 1. EN-TÊTE (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    
    current_bpm = df['BPM'].iloc[-1] if not df.empty else 0
    
    with col1:
        st.markdown(f"<div class='metric-card'><h3>❤️ BPM Actuel</h3><div class='big-stat'>{current_bpm}</div></div>", unsafe_allow_html=True)
    
    with col2:
        # Couleur dynamique pour le Strain
        strain_color = "#34c759" if strain_score < 10 else ("#ff9500" if strain_score < 15 else "#ff3b30")
        st.markdown(f"<div class='metric-card'><h3>🏋️ Strain (0-21)</h3><div class='big-stat' style='color:{strain_color}'>{strain_score:.1f}</div></div>", unsafe_allow_html=True)
        
    with col3:
        # VFC Instantanée
        st.markdown(f"<div class='metric-card'><h3>⚡ VFC (ms)</h3><div class='hrv-stat'>{int(instant_hrv)}</div><small>Stress Monitor</small></div>", unsafe_allow_html=True)

    with col4:
        # Durée
        duration = df['Timestamp'].max() - df['Timestamp'].min()
        st.markdown(f"<div class='metric-card'><h3>⏱️ Durée</h3><div class='big-stat' style='color:#fff'>{str(duration).split('.')[0]}</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    # 2. GRAPHIQUES
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("📈 Rythme Cardiaque (Temps Réel)")
        # On garde les 300 derniers points pour la lisibilité
        chart_data = df.tail(300)
        
        # Graphique BPM avec ligne de couleur selon la zone
        line_chart = alt.Chart(chart_data).mark_line(point=False).encode(
            x=alt.X('Timestamp', axis=alt.Axis(format='%H:%M:%S', title='Heure')),
            y=alt.Y('BPM', scale=alt.Scale(domain=[40, MAX_HR])),
            color=alt.Color('BPM', scale=alt.Scale(scheme='turbo'), legend=None),
            tooltip=['Timestamp', 'BPM', 'Zone']
        ).properties(height=350)
        
        st.altair_chart(line_chart, use_container_width=True)

    with c2:
        st.subheader("📊 Zones d'Effort")
        # Histogramme des zones
        zone_counts = df['Zone'].value_counts()
        zone_df = pd.DataFrame({'Zone': zone_counts.index, 'Points': zone_counts.values})
        
        # Ordre imposé
        zones_order = ['Repos', 'Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5']
        
        bar_chart = alt.Chart(zone_df).mark_bar().encode(
            x=alt.X('Zone', sort=zones_order),
            y='Points',
            color=alt.Color('Zone', scale=alt.Scale(
                domain=zones_order,
                range=['#6b7280', '#9ca3af', '#3b82f6', '#10b981', '#f59e0b', '#ef4444']
            ))
        ).properties(height=350)
        
        st.altair_chart(bar_chart, use_container_width=True)

    # 3. MONITOR DE STRESS (HRV)
    st.subheader("🧠 Analyse Système Nerveux (Expérimental)")
    
    stress_col1, stress_col2 = st.columns([3, 1])
    with stress_col1:
        # Explication
        if instant_hrv > 50:
            st.success(f"**VFC Élevée ({int(instant_hrv)} ms)** : Votre corps est détendu ou en récupération. Système parasympathique dominant.")
        elif instant_hrv > 20:
            st.warning(f"**VFC Moyenne ({int(instant_hrv)} ms)** : Niveau de stress modéré ou activité physique légère.")
        else:
            st.error(f"**VFC Basse ({int(instant_hrv)} ms)** : Stress élevé ou effort intense. Système sympathique dominant.")

except Exception as e:
    # En cas d'erreur de lecture (conflit fichier), on ignore et on réessaie
    # st.error(f"Erreur: {e}") 
    pass

# Auto-refresh
time.sleep(1)
st.rerun()