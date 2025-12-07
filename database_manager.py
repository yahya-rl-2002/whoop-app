
import sqlite3
import datetime
import os
from typing import Optional, List, Tuple

DB_NAME = "whoop.db"

class DatabaseManager:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """Crée une connexion thread-safe"""
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def init_db(self):
        """Initialise le schéma de la base de données"""
        conn = self.get_connection()
        c = conn.cursor()
        
        # Table Sessions
        c.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                device_name TEXT,
                notes TEXT
            )
        ''')
        
        # Table Measurements (Mesures)
        c.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TIMESTAMP,
                bpm INTEGER,
                rr_intervals TEXT, -- Stocké en string "800;810;..."
                battery INTEGER,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        ''')
        
        # Migration : Ajout colonne steps si elle manque
        try:
            c.execute('ALTER TABLE measurements ADD COLUMN steps INTEGER DEFAULT 0')
        except:
            pass # La colonne existe déjà
        
        conn.commit()
        conn.close()

    def create_session(self, device_name: str = "Whoop 4.0") -> int:
        """Crée une nouvelle session et retourne son ID"""
        conn = self.get_connection()
        c = conn.cursor()
        now = datetime.datetime.now()
        
        c.execute('INSERT INTO sessions (start_time, device_name) VALUES (?, ?)', 
                  (now, device_name))
        session_id = c.lastrowid
        conn.commit()
        conn.close()
        return session_id

    def end_session(self, session_id: int):
        """Marque la fin d'une session"""
        conn = self.get_connection()
        c = conn.cursor()
        now = datetime.datetime.now()
        c.execute('UPDATE sessions SET end_time = ? WHERE id = ?', (now, session_id))
        conn.commit()
        conn.close()

    def insert_measurement(self, session_id: int, bpm: int, rr_str: str, battery: int, steps: int = 0):
        """Insère une mesure atomique"""
        conn = self.get_connection()
        c = conn.cursor()
        now = datetime.datetime.now()
        
        c.execute('''
            INSERT INTO measurements (session_id, timestamp, bpm, rr_intervals, battery, steps)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, now, bpm, rr_str, battery, steps))
        
        conn.commit()
        conn.close()

    def get_all_sessions(self) -> List[Tuple]:
        """Récupère l'historique des sessions pour le menu déroulant"""
        conn = self.get_connection()
        c = conn.cursor()
        # On récupère ID + Start Time + Nb Mesures (pour info)
        c.execute('''
            SELECT s.id, s.start_time, s.end_time, COUNT(m.id) as count
            FROM sessions s
            LEFT JOIN measurements m ON s.id = m.session_id
            GROUP BY s.id
            ORDER BY s.start_time DESC
        ''')
        rows = c.fetchall()
        conn.close()
        return rows

    def get_session_data(self, session_id: int):
        """Récupère toutes les mesures d'une session (Compatible Pandas)"""
        # Note: Pour pandas on utilisera directement pd.read_sql avec une connexion brute
        # Cette méthode est un helper si on veut des raw tuples
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT timestamp, bpm, rr_intervals, battery FROM measurements WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_avg_rmssd_7_days(self):
        """Calcule la VFC moyenne (RMSSD) des sessions des 7 derniers jours"""
        conn = self.get_connection()
        try:
            seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
            # On récupère toutes les sessions des 7 derniers jours
            sessions = conn.execute(
                "SELECT id FROM sessions WHERE start_time > ?", 
                (seven_days_ago,)
            ).fetchall()
            
            total_rmssd = []
            
            for s in sessions:
                sid = s[0]
                rows = conn.execute("SELECT rr_intervals FROM measurements WHERE session_id = ?", (sid,)).fetchall()
                session_rrs = []
                for r in rows:
                    if r[0]: session_rrs.extend([int(x) for x in r[0].split(';') if x.strip()])
                
                if len(session_rrs) > 10:
                    diffs = [session_rrs[i+1]-session_rrs[i] for i in range(len(session_rrs)-1)]
                    sq_diffs = [d*d for d in diffs]
                    rmssd = (sum(sq_diffs)/len(sq_diffs))**0.5
                    total_rmssd.append(rmssd)
            
            conn.close()
            if not total_rmssd: return 0
            return sum(total_rmssd) / len(total_rmssd)
        except Exception as e:
            print(f"Avg 7d error: {e}")
            conn.close()
            return 0

    def get_sleep_duration_last_24h(self):
        """Calcule la durée totale de sommeil sur les dernières 24h"""
        conn = self.get_connection()
        try:
            yesterday = datetime.datetime.now() - datetime.timedelta(hours=24)
            # On cherche les sessions > 30 min avec BPM moyen bas (<65) et peu de mouvements (si on avait la colonne)
            # Ici on va faire une approximation basée sur BPM et heure (nuit) si on n'a pas steps dans sessions
            # Idéalement il faudrait stocker 'is_sleep' dans sessions.
            # On va scanner les sessions récentes.
            
            sessions = conn.execute(
                "SELECT id, start_time, end_time FROM sessions WHERE start_time > ?", 
                (yesterday,)
            ).fetchall()
            
            total_sleep_seconds = 0
            
            for s in sessions:
                sid, start, end = s[0], s[1], s[2]
                if not end: continue # Session en cours
                
                # Conversion Str -> Datetime si nécessaire (SQLite renvoie souvent des str)
                if isinstance(start, str):
                    try: start = datetime.datetime.fromisoformat(start)
                    except: continue
                if isinstance(end, str):
                    try: end = datetime.datetime.fromisoformat(end)
                    except: continue
                
                # Récup stats rapides
                row = conn.execute(
                    "SELECT AVG(bpm) as avg_bpm, SUM(steps) as total_steps FROM measurements WHERE session_id = ?", 
                    (sid,)
                ).fetchone()
                
                avg_bpm = row[0] or 0
                total_steps = row[1] or 0
                duration = (end - start).total_seconds()
                
                # Heuristique Sommeil (Même que data_science mais inline pour perf DB)
                # BPM < 65 et Peu de pas (< 100/heure) et Durée > 20 min
                if avg_bpm < 65 and total_steps < 100 and duration > 1200:
                    total_sleep_seconds += duration
            
            conn.close()
            
            # Formatage "Xh YY"
            hours = int(total_sleep_seconds // 3600)
            minutes = int((total_sleep_seconds % 3600) // 60)
            return f"{hours}h {minutes:02d}"
            
        except Exception as e:
            print(f"Sleep calc error: {e}")
            conn.close()
            return "0h 00"
