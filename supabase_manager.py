
import os
from typing import Optional, List, Tuple
from datetime import datetime
from supabase import create_client, Client
import yaml

class SupabaseManager:
    def __init__(self):
        # Charger la config pour Supabase
        try:
            with open("config.yaml", "r") as f:
                config = yaml.safe_load(f)
                supabase_url = config.get('supabase', {}).get('url') or os.getenv('SUPABASE_URL')
                supabase_key = config.get('supabase', {}).get('anon_key') or os.getenv('SUPABASE_ANON_KEY')
        except:
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL et Key doivent être configurés dans config.yaml ou variables d'environnement")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.init_db()

    def init_db(self):
        """Vérifie que les tables existent (créées via SQL dans Supabase)"""
        # Les tables sont créées via supabase_setup.sql
        # On vérifie juste qu'on peut se connecter
        try:
            self.supabase.table('measurements').select('id').limit(1).execute()
        except Exception as e:
            print(f"⚠️ Vérifiez que les tables existent dans Supabase: {e}")

    def get_active_session_id(self) -> Optional[str]:
        """
        Récupère l'ID de la session active.
        On utilise un champ 'session_id' dans measurements pour grouper les données.
        La session active est celle avec le dernier created_at sans session_id fermé.
        """
        try:
            # Récupérer la dernière mesure pour obtenir le session_id actuel
            result = self.supabase.table('measurements')\
                .select('session_id')\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                return result.data[0].get('session_id')
            return None
        except Exception as e:
            print(f"Erreur get_active_session: {e}")
            return None

    def create_or_get_active_session(self) -> str:
        """
        Crée ou récupère la session active.
        Retourne un session_id unique (timestamp-based).
        """
        active_session = self.get_active_session_id()
        if active_session:
            return active_session
        
        # Créer une nouvelle session (utilise timestamp comme ID)
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return session_id

    def insert_measurement(self, session_id: Optional[str] = None, bpm: int = 0, 
                          hrv: Optional[float] = None, strain: Optional[float] = None,
                          battery: int = 0, steps: int = 0, 
                          timestamp: Optional[str] = None, device: str = "python_logger"):
        """
        Insère une mesure dans Supabase.
        Si session_id est None, utilise la session active ou en crée une.
        """
        # Récupérer ou créer la session active
        if session_id is None:
            session_id = self.create_or_get_active_session()
        
        # Préparer les données
        data = {
            "bpm": bpm,
            "session_id": session_id,
            "device": device,
            "steps": steps or 0
        }
        
        if hrv is not None:
            data["hrv"] = hrv
        if strain is not None:
            data["strain"] = strain
        if timestamp:
            data["created_at"] = timestamp
        
        try:
            result = self.supabase.table('measurements').insert(data).execute()
            return session_id
        except Exception as e:
            print(f"Erreur insert measurement: {e}")
            raise

    def get_all_sessions(self) -> List[Tuple]:
        """Récupère toutes les sessions distinctes avec leurs stats"""
        try:
            # Récupérer toutes les sessions distinctes
            result = self.supabase.table('measurements')\
                .select('session_id, created_at')\
                .execute()
            
            # Grouper par session_id
            sessions_dict = {}
            for row in result.data:
                sid = row.get('session_id')
                if sid and sid not in sessions_dict:
                    sessions_dict[sid] = {
                        'id': sid,
                        'start_time': row.get('created_at'),
                        'count': 0
                    }
                if sid:
                    sessions_dict[sid]['count'] += 1
            
            # Convertir en liste de tuples (compatible avec l'ancien format)
            sessions = []
            for sid, data in sorted(sessions_dict.items(), key=lambda x: x[1]['start_time'], reverse=True):
                sessions.append((sid, data['start_time'], None, data['count']))
            
            return sessions
        except Exception as e:
            print(f"Erreur get_all_sessions: {e}")
            return []

    def get_session_data(self, session_id: str):
        """Récupère toutes les mesures d'une session"""
        try:
            result = self.supabase.table('measurements')\
                .select('*')\
                .eq('session_id', session_id)\
                .order('created_at', desc=False)\
                .execute()
            
            return result.data
        except Exception as e:
            print(f"Erreur get_session_data: {e}")
            return []

    def end_session(self, session_id: str):
        """Marque la fin d'une session (pas de colonne end_time, on utilise juste le session_id)"""
        # Dans Supabase, on n'a pas de table sessions séparée
        # On peut ajouter un champ 'session_ended' si nécessaire
        # Pour l'instant, on ne fait rien car la session se termine naturellement
        pass

