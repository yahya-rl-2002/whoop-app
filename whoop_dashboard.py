
import streamlit as st
import pandas as pd
import glob
import os
import time
import altair as alt

# Configuration de la page
st.set_page_config(
    page_title="Whoop Live Monitor",
    page_icon="💓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Constantes
MAX_HR = 190
REFRESH_RATE = 2 # secondes

# CSS personnalisé pour un look "Whoop" (Sombre et Minimaliste)
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    .metric-container {
        backround-color: #262730;
        border-radius: 10px;
        padding: 10px;
    }
    /* Gros chiffre pour le BPM actuel */
    .big-font {
        font-size: 80px !important;
        font-weight: 700;
        color: #ff3b30;
    }
</style>
""", unsafe_allow_html=True)

def get_latest_csv():
    """Trouve le fichier CSV le plus récent."""
    list_of_files = glob.glob('whoop_session_*.csv') 
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getctime)

def calculate_zones_and_strain(df):
    """Calcule les zones et le strain score."""
    if df.empty:
        return df, 0
        
    def get_zone(bpm):
        pct = bpm / MAX_HR
        if pct < 0.50: return 'Hors Zone', 0
        if pct < 0.60: return 'Zone 1', 1
        if pct < 0.70: return 'Zone 2', 2
        if pct < 0.80: return 'Zone 3', 3
        if pct < 0.90: return 'Zone 4', 4
        return 'Zone 5', 5

    # Appliquer le calcul de zone
    df['Zone_Tuple'] = df['BPM'].apply(get_zone)
    df['Zone'] = df['Zone_Tuple'].apply(lambda x: x[0])
    # Z_Score n'est pas utilisé pour le strain complexe ici, mais utile potentiellement
    
    # Calcul des durées entre points (approx)
    # Pour un stream live, on peut simplifier en supposant 1s par point si régulier, 
    # mais calculons le delta réel pour être précis.
    df['Delta_Sec'] = df['Timestamp'].diff().dt.total_seconds().fillna(1.0) # 1s par défaut pour le 1er point
    
    # Calcul du Strain : Somme pondérée
    # (Temps Z3 * 1) + (Temps Z4 * 2) + (Temps Z5 * 3)
    # On va le faire en secondes puis convertir
    
    df['Strain_Weight'] = 0.0
    df.loc[df['Zone'] == 'Zone 3', 'Strain_Weight'] = 1.0
    df.loc[df['Zone'] == 'Zone 4', 'Strain_Weight'] = 2.0
    df.loc[df['Zone'] == 'Zone 5', 'Strain_Weight'] = 3.0
    
    total_strain_raw = (df['Strain_Weight'] * df['Delta_Sec']).sum()
    
    # Facteur arbitraire pour ramener ça à un score lisible (ex: 0-21)
    # Disons que 1h en Zone 5 = 3600 * 3 = 10800 raw points.
    # Si on veut que ça fasse 21... divisons par ~500 ?
    # Pour l'instant, faisons / 60 pour avoir des "minutes d'effort pondérées"
    strain_score = total_strain_raw / 60.0 
    
    return df, strain_score

# ==========================================
# MAIN APP LOGIC
# ==========================================

st.title("💓 Whoop Live Dashboard")

# 1. Chargement du fichier
csv_file = get_latest_csv()

if not csv_file:
    st.warning("⚠️ En attente de connexion du bracelet... (Aucun fichier CSV trouvé)")
    time.sleep(REFRESH_RATE)
    st.rerun()

try:
    # Lecture robuste
    df = pd.read_csv(csv_file, skipinitialspace=True)
    
    if df.empty or 'Timestamp' not in df.columns or 'BPM' not in df.columns:
        st.info("⏳ Fichier détecté, en attente de données...")
        time.sleep(REFRESH_RATE)
        st.rerun()

    # Nettoyage
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Calculs
    df, strain = calculate_zones_and_strain(df)
    
    # KPIs
    current_bpm = df['BPM'].iloc[-1]
    max_bpm = df['BPM'].max()
    start_time = df['Timestamp'].min()
    end_time = df['Timestamp'].max()
    duration = end_time - start_time
    duration_str = str(duration).split('.')[0] # Enlève les ms
    
    # --- UI LAYOUT ---
    
    # Ligne 1 : KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(label="BPM Actuel", value=f"{current_bpm}")
    with col2:
        st.metric(label="BPM Max", value=f"{max_bpm}")
    with col3:
        st.metric(label="Durée Session", value=duration_str)
    with col4:
        st.metric(label="Strain (Score)", value=f"{strain:.1f}")

    st.markdown("---")

    # Ligne 2 : Graphiques
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("BPM en Direct")
        # Line Chart simple mais efficace
        # On garde les 500 derniers points pour la fluidité si la session est longue
        chart_data = df[['Timestamp', 'BPM']].tail(1000)
        st.line_chart(chart_data, x='Timestamp', y='BPM', color='#ff3b30')

    with c2:
        st.subheader("Zones d'Effort")
        # Bar Chart des zones
        if 'Duration_Sec' not in df.columns:
             df['Duration_Sec'] = df['Timestamp'].diff().shift(-1).dt.total_seconds().fillna(1.0)

        zone_counts = df.groupby('Zone')['Duration_Sec'].sum() / 60 # En minutes
        
        # On s'assure d'avoir l'ordre correct et toutes les zones
        zones_order = ['Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5']
        zone_data = pd.DataFrame({
            'Zone': zones_order,
            'Minutes': [zone_counts.get(z, 0.0) for z in zones_order]
        })
        
        # Bar chart avec couleurs personnalisées via Altair pour plus de contrôle que st.bar_chart
        chart = alt.Chart(zone_data).mark_bar().encode(
            x=alt.X('Zone', sort=None),
            y='Minutes',
            color=alt.Color('Zone', scale=alt.Scale(
                domain=['Zone 1', 'Zone 2', 'Zone 3', 'Zone 4', 'Zone 5'],
                range=['#8e8e93', '#007aff', '#34c759', '#ff9500', '#ff3b30']
            ))
        )
        st.altair_chart(chart, use_container_width=True)

    # Indicateur de fichier source
    st.caption(f"Source : `{csv_file}` | Max HR Config : `{MAX_HR}`")

except Exception as e:
    st.error(f"Erreur de lecture : {e}")
    # En cas d'erreur (ex: fichier verrouillé), on attend et on réessaie
    pass

# Boucle de rafraîchissement
time.sleep(REFRESH_RATE)
st.rerun()
