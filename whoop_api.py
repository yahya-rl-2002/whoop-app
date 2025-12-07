
from fastapi import FastAPI
from database_manager import DatabaseManager
import uvicorn
import pandas as pd

app = FastAPI(title="Whoop Pro API", version="1.0.0")
db = DatabaseManager()

@app.get("/")
def read_root():
    return {"status": "Whoop API Running", "docs": "/docs"}

@app.get("/current")
def get_current_metrics():
    """Retourne les dernières métriques connues (BPM, Batterie, Pas)"""
    # On récupère la dernière session active
    sessions = db.get_all_sessions()
    if not sessions: return {"error": "No session"}
    
    last_session_id = sessions[0][0]
    
    # On lit la dernière ligne
    conn = db.get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM measurements WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
        conn,
        params=(last_session_id,)
    )
    conn.close()
    
    if df.empty: return {"status": "Waiting for data"}
    
    row = df.iloc[0]
    return {
        "bpm": int(row['bpm']),
        "battery": int(row['battery']),
        "steps": int(row['steps']) if 'steps' in row else 0,
        "timestamp": str(row['timestamp'])
    }

if __name__ == "__main__":
    # Écoute sur 0.0.0.0 pour être accessible sur le réseau local (Wifi)
    uvicorn.run(app, host="0.0.0.0", port=8000)
