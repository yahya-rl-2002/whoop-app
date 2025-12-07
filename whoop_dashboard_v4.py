
import streamlit as st
import pandas as pd
import time
import numpy as np
import altair as alt
import yaml # Import YAML
from database_manager import DatabaseManager

# Chargement Config
try:
    with open("config.yaml", "r") as f:
        CONFIG = yaml.safe_load(f)
except:
    CONFIG = {"user": {"max_hr": 190}, "app": {"refresh_rate": 1}}

# --- CONFIGURATION STREAMLIT ---
st.set_page_config(page_title="Whoop Pro V4", page_icon="🏆", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #000000; color: #e0e0e0; }
    .metric-box {
        background-color: #1a1a1a; border: 1px solid #333;
        border-radius: 8px; padding: 15px; text-align: center;
    }
    .big-num { font-size: 2.5rem; font-weight: 800; }
    .label { font-size: 0.8rem; color: #888; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# --- INIT DB ---
db = DatabaseManager()

# --- FONCTIONS UTILITAIRES ---
def parse_rr(rr_str):
    if not rr_str: return []
    try: return [int(x) for x in str(rr_str).split(';') if x.strip() and 250 < int(x) < 1500]
    except: return []

def calc_rmssd(rr_list):
    if len(rr_list) < 2: return 0
    diffs = np.diff(rr_list)
    return np.sqrt(np.mean(diffs ** 2))

# --- SIDEBAR (HISTORIQUE) ---
with st.sidebar:
    st.header(f"Profil: {CONFIG.get('user', {}).get('name', 'User')}")
    st.divider()
    
    st.subheader("🗄️ Historique Sessions")
    
    # Récupération des sessions valides
    sessions = db.get_all_sessions() # [(id, start, end, count), ...]
    
    if not sessions:
        st.warning("Aucune session trouvée.")
        selected_session_id = None
        auto_refresh = False
    else:
        # Création d'un dict pour le selectbox : "Session #12 (2023-12-07 19:00)" -> ID
        options = {f"Session #{s[0]} ({str(s[1])[:16]}) - {s[3]} pts": s[0] for s in sessions}
        
        # Par défaut, on sélectionne la plus récente (la première de la liste triée DESC)
        selected_label = st.selectbox("Choisir une session :", options.keys())
        selected_session_id = options[selected_label]
        
        auto_refresh = st.toggle("🔴 Mode Live (Auto-Refresh)", value=True)

    st.divider()
    # Utilisation de la config pour la valeur par défaut
    default_max_hr = CONFIG['user']['max_hr']
    MAX_HR = st.number_input("Max Heart Rate", 150, 220, default_max_hr)

    # --- REMOTE CONTROL (MOBILE) ---
    st.divider()
    st.subheader("📱 Contrôle Tél")
    
    import subprocess
    import sys
    import os
    import signal

    # Gestion état Processus
    if 'logger_pid' not in st.session_state:
        st.session_state.logger_pid = None
        
    def start_logger():
        if st.session_state.logger_pid is None:
            # On lance le logger en background
            # Note: on utilise sys.executable pour etre sur d'utiliser le meme python
            cmd = [sys.executable, "whoop_logger_v4.py"]
            # Creation process
            p = subprocess.Popen(cmd, cwd=os.getcwd()) #, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            st.session_state.logger_pid = p.pid
            st.toast("✅ Enregistrement Démarré !", icon="🚀")
            
    def stop_logger():
        if st.session_state.logger_pid:
            try:
                os.kill(st.session_state.logger_pid, signal.SIGTERM)
                st.toast("🛑 Enregistrement Arrêté !", icon="⏹️")
            except Exception as e:
                st.error(f"Erreur stop: {e}")
            st.session_state.logger_pid = None
            
    c_start, c_stop = st.columns(2)
    if c_start.button("▶️ START", type="primary", disabled=st.session_state.logger_pid is not None):
        start_logger()
        st.rerun()
        
    if c_stop.button("⏹️ STOP", type="secondary", disabled=st.session_state.logger_pid is None):
        stop_logger()
        st.rerun()

    if st.session_state.logger_pid:
        st.caption(f"🔴 REC en cours (PID: {st.session_state.logger_pid})")
    
    # --- PDF EXPORT ---
    # --- PDF EXPORT ---
    st.divider()
    if selected_session_id:
        if st.button("📄 Générer Rapport PDF"):
            # On doit re-récupérer le DF complet ici ou le passer via session_state
            # Pour faire simple on recharge vite fait
            conn = db.get_connection()
            pdf_df = pd.read_sql_query("SELECT timestamp, bpm, steps FROM measurements WHERE session_id = ? ORDER BY timestamp ASC", conn, params=(selected_session_id,), parse_dates=['timestamp'])
            conn.close()
            
            if not pdf_df.empty:
                from report_generator import generate_pdf_report
                pdf_file = generate_pdf_report(selected_session_id, pdf_df, f"report_session_{selected_session_id}.pdf")
                
                with open(pdf_file, "rb") as f:
                    st.download_button("⬇️ Télécharger PDF", f, file_name=pdf_file)
                st.success("Rapport généré !")

# --- MAIN DASHBOARD ---
if selected_session_id:
    # Lecture SQL vers Pandas
    conn = db.get_connection()
    df = pd.read_sql_query(
        "SELECT timestamp, bpm, rr_intervals, battery, steps FROM measurements WHERE session_id = ? ORDER BY timestamp ASC",
        conn,
        params=(selected_session_id,),
        parse_dates=['timestamp']
    )
    conn.close()

    if df.empty:
        st.info("Session vide ou en cours d'initialisation...")
    else:
        # --- PRE-CALCULS ---
        current_bpm = df['bpm'].iloc[-1]
        current_batt = df['battery'].iloc[-1]
        
        # Pour les pas, on gère le cas où la colonne serait NaN (anciennes sessions)
        if 'steps' not in df.columns: df['steps'] = 0
        total_steps = df['steps'].fillna(0).sum()
        
        from data_science import calculate_respiratory_rate, calculate_recovery_score, analyze_sleep_architecture, detect_stress_event, calculate_body_battery
        
        # VFC
        all_rr = []
        for r in df['rr_intervals'].apply(parse_rr): all_rr.extend(r)
        
        hrv_rmssd = calc_rmssd(all_rr)
        
        # Recovery
        avg_hrv_7d = db.get_avg_rmssd_7_days()
        recovery_score = calculate_recovery_score(hrv_rmssd, avg_hrv_7d)
        
        # Recup dernières valeurs pour Stress
        is_moving = total_steps > (len(df)/60 * 20) 
        stress_detected = detect_stress_event(hrv_rmssd, avg_hrv_7d, current_bpm, is_moving)
        
        if stress_detected:
            st.toast("⚠️ STRESS DÉTECTÉ : Prenez 5 min pour respirer !", icon="🧘")
            
        # Body Battery
        # On passe une liste constante de RMSSD pour simplifier dans cette version
        body_battery = calculate_body_battery(df['bpm'].tolist(), [hrv_rmssd]*len(df))
        
        # Sommeil 24h
        sleep_duration_24h = db.get_sleep_duration_last_24h()
        
        rec_color = "#34c759" if recovery_score > 66 else ("#fbbf24" if recovery_score > 33 else "#ff3b30")
        
        # Calcul RPM (Data Science)
        respiratory_rate = calculate_respiratory_rate(all_rr)
        rpm_display = f"{respiratory_rate}" if respiratory_rate else "--"
        
        # Analyse Sommeil
        from data_science import classify_sleep_phases
        sleep_status = analyze_sleep_architecture(df['bpm'].tolist(), total_steps)

        if sleep_status == "SOMMEIL (Détecté)":
            st.info("😴 Session identifiée comme SOMMEIL (BPM bas & Mouvements faibles)")
            
            # Hypnogramme
            phases = classify_sleep_phases(df['bpm'].tolist())
            # On crée un petit DF pour le graph
            # On aligne phases avec timestamp (approx si windowing, mais classify retourne list complete)
            if len(phases) == len(df):
                df['sleep_phase'] = phases
                
                # Couleurs : Deep (Bleu Foncé), Light (Bleu clair), REM (Violet), Awake (Rose/Rouge)
                phase_colors = alt.Scale(domain=['Deep', 'Light', 'REM', 'Awake'],
                                        range=['#1e3a8a', '#60a5fa', '#a855f7', '#f43f5e'])
                
                hypno_chart = alt.Chart(df).mark_rect().encode(
                    x='timestamp',
                    y=alt.Y('sleep_phase', title='Phase'),
                    color=alt.Color('sleep_phase', scale=phase_colors, legend=None),
                    tooltip=['timestamp', 'sleep_phase', 'bpm']
                ).properties(height=150, title="Architecture du Sommeil (Hypnogramme)")
                
                st.altair_chart(hypno_chart, use_container_width=True)

        # Strain (Approximation logarithmique 0-21)
        # On suppose que chaque point de la série est 1 sec
        df['strain_pts'] = pd.cut(df['bpm'], 
            bins=[0, MAX_HR*0.5, MAX_HR*0.6, MAX_HR*0.7, MAX_HR*0.8, MAX_HR*0.9, 300], 
            labels=[0, 1, 2, 4, 8, 12], include_lowest=True).astype(float)
        
        strain_score = min(21 * (1 - np.exp(-df['strain_pts'].sum() / 6000)), 21.0)
        
        # --- UI KPIS (Ligne 1 : Principaux) ---
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='metric-box'><div class='big-num' style='color:#fff'>{current_bpm}</div><div class='label'>BPM</div></div>", unsafe_allow_html=True)
        
        s_col = "#34c759" if strain_score < 10 else "#ff3b30"
        c2.markdown(f"<div class='metric-box'><div class='big-num' style='color:{s_col}'>{strain_score:.1f}</div><div class='label'>STRAIN</div></div>", unsafe_allow_html=True)
        
        c3.markdown(f"<div class='metric-box'><div class='big-num' style='color:{rec_color}'>{recovery_score}%</div><div class='label'>RÉCUPÉRATION</div><div style='font-size:0.8em; color:#888'>Sommeil: {sleep_duration_24h}</div></div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)

        # Body Battery Bar
        st.markdown(f"**🔋 Body Battery : {int(body_battery)}%**")
        st.progress(int(body_battery)/100)
        st.markdown("<br>", unsafe_allow_html=True)

        # --- UI KPIS (Ligne 2 : Secondaires) ---
        c4, c5, c6 = st.columns(3)
        
        batt_col = "#34c759" if current_batt > 20 else "#ff3b30"
        c4.markdown(f"<div class='metric-box'><div class='big-num' style='color:{batt_col}'>{current_batt}%</div><div class='label'>BATTERIE</div></div>", unsafe_allow_html=True)

        c5.markdown(f"<div class='metric-box'><div class='big-num' style='color:#3b82f6'>{int(total_steps)}</div><div class='label'>PAS (Est.)</div></div>", unsafe_allow_html=True)
        
        c6.markdown(f"<div class='metric-box'><div class='big-num' style='color:#a855f7'>{rpm_display}</div><div class='label'>RESPIRATION (RPM)</div></div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # --- GRAPHIQUE ---
        st.subheader("📈 Courbe Cardiaque")
        chart = alt.Chart(df).mark_area(
            line={'color':'#ff3b30'},
            color=alt.Gradient(gradient='linear', stops=[alt.GradientStop(color='#ff3b30', offset=0), alt.GradientStop(color='transparent', offset=1)], x1=1, x2=1, y1=1, y2=0)
        ).encode(
            x=alt.X('timestamp', axis=alt.Axis(format='%H:%M:%S', title='Heure')),
            y=alt.Y('bpm', scale=alt.Scale(domain=[40, MAX_HR]), title='BPM'),
            tooltip=['timestamp', 'bpm', 'steps']
        ).properties(height=400)
        st.altair_chart(chart, use_container_width=True)

else:
    st.title("👈 Sélectionnez une session dans la barre latérale")

if auto_refresh:
    time.sleep(1)
    st.rerun()
