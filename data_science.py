
import numpy as np

def calculate_respiratory_rate(rr_intervals_ms):
    """
    Estime le Taux Respiratoire (RPM) basé sur le Phénomène RSA (Respiratory Sinus Arrhythmia).
    Le coeur accélère à l'inspiration (RR diminue) et ralentit à l'expiration (RR augmente).
    On utilise l'analyse spectrale (FFT) des intervalles RR.
    
    Args:
        rr_intervals_ms (list): Liste des intervalles RR en millisecondes.
        
    Returns:
        float: Respirations par minute (RPM) ou None si pas assez de données.
    """
    if not rr_intervals_ms or len(rr_intervals_ms) < 30: # Besoin de ~30sec de données min
        return None

    # 1. Conversion en série temporelle régulière (Rééchantillonnage)
    # Les RR sont irréguliers dans le temps. On veut un signal à 4Hz (tous les 250ms).
    rr_times = np.cumsum(rr_intervals_ms) / 1000.0 # Temps en secondes
    rr_values = np.array(rr_intervals_ms)
    
    # Création axe temps régulier (Intermolation 4Hz)
    fs = 4.0 
    duration = rr_times[-1] - rr_times[0]
    if duration < 10: return None
    
    time_interp = np.arange(rr_times[0], rr_times[-1], 1/fs)
    rr_interp = np.interp(time_interp, rr_times, rr_values)
    
    # 2. Filtrage et Normalisation
    # On enlève la composante continue (DC) et tendances très basses fréquences
    signal = rr_interp - np.mean(rr_interp)
    
    # 3. Fast Fourier Transform (FFT) pour trouver la fréquence dominante
    n = len(signal)
    fft_vals = np.fft.rfft(signal)
    fft_freqs = np.fft.rfftfreq(n, d=1/fs)
    
    # On cherche le pic dans la bande respiratoire (0.1 Hz à 0.5 Hz => 6 à 30 RPM)
    mask = (fft_freqs >= 0.1) & (fft_freqs <= 0.5)
    valid_freqs = fft_freqs[mask]
    valid_power = np.abs(fft_vals[mask]) # Amplitude du spectre
    
    if len(valid_power) == 0: return None
    
    peak_freq = valid_freqs[np.argmax(valid_power)]
    
    # Conversion Hz -> RPM
    rpm = peak_freq * 60
    return round(rpm, 1)


def analyze_sleep_architecture(bpm_series, steps_total):
    """
    Détecte si une session est du sommeil et tente de classifier les phases.
    Critères simples :
    - Pas de mouvement (Steps < 10)
    - BPM bas (< 55 ou < Repos+5)
    - Durée > 30 min
    """
    if not bpm_series or len(bpm_series) < 60: return None
    
    avg_bpm = np.mean(bpm_series)
    duration_min = len(bpm_series) / 60 # Approx 1pt/sec
    
    # Heuristique Sommeil
    if steps_total < 50 and avg_bpm < 65 and duration_min > 20:
        return "SOMMEIL (Détecté)"
    
    return "ACTIVITÉ"

def calculate_recovery_score(current_rmssd, avg_7day_rmssd):
    """
    Calcule le score de récupération (0-100%) basé sur la déviation par rapport à la moyenne.
    """
    if not avg_7day_rmssd or avg_7day_rmssd == 0: return 50 # Neutre par défaut
    
    ratio = current_rmssd / avg_7day_rmssd
    
    # Logique simplifiée Whoop-like
    # > 1.0 (Supérieur à moyenne) => Vert (>66%)
    # 0.8 - 1.0 => Jaune (33-66%)
    # < 0.8 => Rouge (<33%)
    

    if ratio >= 1.05: score = 90 # Boom
    elif ratio >= 0.95: score = 75 # Normal
    elif ratio >= 0.80: score = 50 # Fatigue
    else: score = 20 # Danger
    
    return score

def detect_stress_event(current_rmssd, baseline_rmssd, current_bpm, is_moving=False):
    """
    Détecte un état de stress physiologique si la VFC chute brutalement sans activité physique.
    Retourne True si Stress détecté.
    """
    if is_moving or not baseline_rmssd or baseline_rmssd == 0: return False
    
    # Stress si VFC < 60% de la moyenne ET BPM un peu élevé (> 70 mais pas Sport)
    if current_rmssd < (baseline_rmssd * 0.6) and current_bpm > 70:
        return True
    return False

def calculate_body_battery(bpm_history, rmssd_history):
    """
    Simule une jauge d'énergie (0-100%)
    - Le stress/effort (BPM haut) vide la batterie.
    - Le repos (BPM bas + HRV haut) la recharge.
    Pour simplifier, on recalcule depuis le début de la session.
    Départ supposé : 80% (Matin standard)
    """
    battery = 80.0
    for bpm, hrv in zip(bpm_history, rmssd_history):
        # Logique simplifiée
        # Effort : BPM > 100 -> Perte 0.05% par point (supposé 1-5sec)
        # Repos : BPM < 60 -> Gain 0.02% par point
        
        if bpm > 100:
            drain = (bpm - 100) * 0.001 # Plus on force plus ça descend vite
            battery -= drain
        elif bpm < 65:
            recharge = 0.02
            battery += recharge
        # Stress (HRV bas mais BPM calme) -> Perte légère
        elif hrv < 20: 
            battery -= 0.01
            
        battery = max(0, min(100, battery))
        
    return battery

def classify_sleep_phases(bpm_series):
    """
    Retourne une liste de phases (Deep, Light, REM, Awake) basée sur des heuristiques.
    Simule un hypnogramme.
    """
    phases = []
    # Lissage simple
    window = 5
    for i in range(0, len(bpm_series), window):
        chunk = bpm_series[i:i+window]
        if not chunk: continue
        avg = sum(chunk)/len(chunk)
        std = np.std(chunk)
        
        # Deep : BPM très bas et très stable
        if avg < 55 and std < 2: phase = "Deep"
        # REM : BPM moyen mais variable (rêves)
        elif 55 <= avg < 70 and std > 5: phase = "REM"
        # Light : BPM moyen et stable
        elif 55 <= avg < 70: phase = "Light"
        # Awake : BPM haut
        else: phase = "Awake"
        
        # On répète la phase pour la fenêtre
        phases.extend([phase] * len(chunk))
        
    return phases

