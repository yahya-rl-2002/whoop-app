
from fpdf import FPDF
import pandas as pd
import datetime

class WhoopReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Whoop Pro V4 - Session Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(session_id, df: pd.DataFrame, file_name="report.pdf"):
    pdf = WhoopReport()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    # 1. Infos Session
    start_time = df['timestamp'].iloc[0].strftime("%Y-%m-%d %H:%M:%S")
    end_time = df['timestamp'].iloc[-1].strftime("%H:%M:%S")
    duration = str(df['timestamp'].iloc[-1] - df['timestamp'].iloc[0])
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f"Session #{session_id} - {start_time}", 0, 1, 'L', 1)
    pdf.ln(5)
    
    pdf.cell(0, 8, f"Durée: {duration}", 0, 1)
    pdf.cell(0, 8, f"Max BPM: {df['bpm'].max()}", 0, 1)
    pdf.cell(0, 8, f"Moyenne BPM: {int(df['bpm'].mean())}", 0, 1)
    
    if 'steps' in df.columns:
        pdf.cell(0, 8, f"Pas Totaux: {int(df['steps'].sum())}", 0, 1)

    pdf.ln(10)
    
    # 2. Analyse Zones (Simulation simple)
    # (Un vrai chart serait mieux, on fera texte pour l'instant)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Résumé des Zones d'Effort", 0, 1)
    pdf.set_font('Arial', '', 11)
    
    # On pourrait réutiliser la logique des zones ici
    
    pdf.multi_cell(0, 8, "Ce rapport certifie l'activité physique enregistrée par le système Whoop Clone V4.")
    
    pdf.output(file_name)
    return file_name
