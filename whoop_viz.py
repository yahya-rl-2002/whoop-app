
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import glob
import os
import sys

# ==========================================
# CONFIGURATION
# ==========================================
MAX_HR = 190  # Fréquence Cardiaque Maximale

# Définition des zones (Pourcentages de MAX_HR)
ZONES_CONFIG = {
    'Zone 1': (0.50, 0.60, '#8e8e93'),  # Gris (Récupération)
    'Zone 2': (0.60, 0.70, '#007aff'),  # Bleu (Endurance)
    'Zone 3': (0.70, 0.80, '#34c759'),  # Vert (Aérobie)
    'Zone 4': (0.80, 0.90, '#ff9500'),  # Orange (Seuil)
    'Zone 5': (0.90, 1.01, '#ff3b30')   # Rouge (Max) - 1.01 pour inclure 100%
}

def get_latest_csv():
    """Trouve le fichier 'whoop_session_*.csv' le plus récent dans le dossier courant."""
    list_of_files = glob.glob('whoop_session_*.csv') 
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getctime)

def calculate_zones(df):
    """Calcule la zone pour chaque point et le temps passé par zone."""
    
    def get_zone(bpm):
        pct = bpm / MAX_HR
        if pct < 0.50: return 'Hors Zone'
        if pct < 0.60: return 'Zone 1'
        if pct < 0.70: return 'Zone 2'
        if pct < 0.80: return 'Zone 3'
        if pct < 0.90: return 'Zone 4'
        return 'Zone 5'

    # Attribution de la zone pour chaque ligne
    df['Zone'] = df['BPM'].apply(get_zone)
    
    # Calcul du temps écoulé entre chaque point
    # On calcule la différence avec le point SUIVANT pour savoir combien de temps
    # on est resté à cette valeur de BPM.
    df['Duration_Sec'] = df['Timestamp'].diff().shift(-1).dt.total_seconds()
    
    # Pour la dernière ligne, on assume la médiane des intervalles précédents ou 1s par défaut
    median_interval = df['Duration_Sec'].median()
    if pd.isna(median_interval): median_interval = 1.0
    df.fillna({'Duration_Sec': median_interval}, inplace=True)
    
    return df

def analyze_session(filename):
    print(f"📊 Analyse du fichier : {filename}")
    
    try:
        # Chargement des données
        df = pd.read_csv(filename, skipinitialspace=True)
        
        if 'Timestamp' not in df.columns or 'BPM' not in df.columns:
            print("❌ Erreur: Colonnes manquantes.")
            return

        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # 1. Calcul des Zones
        df = calculate_zones(df)

        # 2. Stats globales
        duration = df['Timestamp'].max() - df['Timestamp'].min()
        print("\n📈 Statistiques de la session :")
        print(f"   ⏱️  Durée : {duration}")
        print(f"   💓 Moyenne : {df['BPM'].mean():.1f} BPM")
        print(f"   🔥 Max HR configurée : {MAX_HR} BPM")

        # 3. Stats par Zone
        # Group by Zone et somme des durées
        zone_stats = df.groupby('Zone')['Duration_Sec'].sum().reset_index()
        
        # On s'ure que toutes les zones sont présentes même si temps = 0
        all_zones = list(ZONES_CONFIG.keys())
        zone_stats = zone_stats.set_index('Zone').reindex(all_zones).fillna(0).reset_index()
        
        zone_stats['Minutes'] = zone_stats['Duration_Sec'] / 60
        
        print("\n📊 Temps passé par Zone :")
        for _, row in zone_stats.iterrows():
            z_name = row['Zone']
            minutes = row['Minutes']
            print(f"   {z_name}: {minutes:.1f} min")

        # 4. Visualisation (Dashboard)
        plt.style.use('dark_background') # Style plus "Sport/Tech"
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [2, 1]})
        fig.suptitle(f'Analyse Session Whoop - {filename}', fontsize=16)

        # --- Graph 1 : Courbe BPM ---
        # On peut colorer la ligne par segments, mais c'est complexe en plot standard.
        # On va faire simple : Ligne blanche + background coloré par zone
        ax1.plot(df['Timestamp'], df['BPM'], color='white', linewidth=2, label='BPM')
        
        # Colorer le fond selon les zones
        start_time = df['Timestamp'].min()
        end_time = df['Timestamp'].max()
        
        for z_name, (low, high, color) in ZONES_CONFIG.items():
            ax1.axhspan(low*MAX_HR, high*MAX_HR, color=color, alpha=0.2, label=z_name)
            
        ax1.set_ylabel('BPM')
        ax1.set_title('Fréquence Cardiaque & Zones')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper right', fontsize='small')
        
        # Format date axe X
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # --- Graph 2 : Bar Chart Zones ---
        # Préparation des couleurs
        bar_colors = [ZONES_CONFIG[z][2] for z in zone_stats['Zone']]
        
        bars = ax2.bar(zone_stats['Zone'], zone_stats['Minutes'], color=bar_colors, alpha=0.8)
        
        ax2.set_ylabel('Minutes')
        ax2.set_title('Temps passé par Zone d\'Effort')
        ax2.grid(axis='y', alpha=0.3)
        
        # Ajouter les valeurs sur les barres
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}m',
                    ha='center', va='bottom')

        # Finalisation
        print("\n🖼️  Ouverture du Dashboard...")
        plt.tight_layout()
        plt.show()

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse : {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        target_file = get_latest_csv()

    if target_file:
        analyze_session(target_file)
    else:
        print("⚠️  Aucun fichier CSV trouvé.")
