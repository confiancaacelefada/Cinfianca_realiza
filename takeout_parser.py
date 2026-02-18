# google_takeout_parser.py
# Script para parsing de Google Takeout (foco em Location History + metadados)
# Uso: python google_takeout_parser.py --takeout_dir /caminho/para/pasta/Takeout

import json
import os
import argparse
import pandas as pd
from datetime import datetime
from pathlib import Path
from tqdm import tqdm
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Parser de Google Takeout para metadados de rotina")
    parser.add_argument("--takeout_dir", required=True, help="Caminho para a pasta descompactada do Takeout")
    parser.add_argument("--output_dir", default="output", help="Pasta para salvar CSVs e relatórios")
    return parser.parse_args()

def load_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar {file_path}: {e}")
        return None

def parse_location_history(semantic_dir):
    locations = []
    json_files = list(Path(semantic_dir).glob("*.json"))
    
    for file in tqdm(json_files, desc="Processando Semantic Location History"):
        data = load_json(file)
        if not data or 'timelineObjects' not in data:
            continue
        
        for obj in data['timelineObjects']:
            if 'placeVisit' in obj:
                visit = obj['placeVisit']
                loc = visit.get('location', {})
                timestamp = visit.get('durationStartTimestampMs') or visit.get('centerLatE7')
                if timestamp:
                    dt = datetime.fromtimestamp(int(timestamp) / 1000)
                    locations.append({
                        'timestamp': dt.isoformat(),
                        'latitude': loc.get('latitudeE7', 0) / 1e7,
                        'longitude': loc.get('longitudeE7', 0) / 1e7,
                        'address': loc.get('address', 'Desconhecido'),
                        'place_id': loc.get('placeId'),
                        'duration_ms': visit.get('duration', 'PT0S'),
                        'source': 'semantic'
                    })
    
    if locations:
        df = pd.DataFrame(locations)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    return pd.DataFrame()

def parse_records_json(records_path):
    data = load_json(records_path)
    if not data or 'locations' not in data:
        return pd.DataFrame()
    
    locations = []
    for loc in tqdm(data['locations'], desc="Processando Records.json"):
        ts = loc.get('timestampMs')
        if ts:
            dt = datetime.fromtimestamp(int(ts) / 1000)
            locations.append({
                'timestamp': dt.isoformat(),
                'latitude': loc.get('latitudeE7', 0) / 1e7,
                'longitude': loc.get('longitudeE7', 0) / 1e7,
                'accuracy': loc.get('accuracy', None),
                'velocity': loc.get('velocity', None),
                'altitude': loc.get('altitude', None),
                'source': 'records'
            })
    
    if locations:
        df = pd.DataFrame(locations)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    return pd.DataFrame()

def analyze_anomalies(df_location):
    if df_location.empty:
        return {"score_location": 100, "anomalies": []}
    
    df_location['duration_hours'] = pd.to_timedelta(df_location.get('duration_ms', 'PT0S')).dt.total_seconds() / 3600
    suspicious = df_location[
        (df_location['address'].str.contains('Desconhecido', na=False)) &
        (df_location['duration_hours'] > 2)
    ]
    
    anomalies = suspicious.to_dict('records')
    score = max(0, 100 - len(anomalies) * 5)
    
    return {
        "score_location": score,
        "anomalies_count": len(anomalies),
        "anomalies_sample": anomalies[:3]
    }

def main():
    args = parse_arguments()
    takeout_path = Path(args.takeout_dir)
    output_path = Path(args.output_dir)
    output_path.mkdir(exist_ok=True)
    
    print(f"Processando Takeout em: {takeout_path}")
    
    semantic_dir = takeout_path / "Location History" / "Semantic Location History"
    df_semantic = parse_location_history(semantic_dir) if semantic_dir.exists() else pd.DataFrame()
    
    records_path = takeout_path / "Location History" / "Records.json"
    df_records = parse_records_json(records_path) if records_path.exists() else pd.DataFrame()
    
    if not df_semantic.empty and not df_records.empty:
        df_all = pd.concat([df_semantic, df_records]).sort_values('timestamp').reset_index(drop=True)
    elif not df_semantic.empty:
        df_all = df_semantic
    elif not df_records.empty:
        df_all = df_records
    else:
        df_all = pd.DataFrame()
    
    if not df_all.empty:
        df_all.to_csv(output_path / "location_history_merged.csv", index=False)
        print(f"Salvo: {len(df_all)} entradas de localização")
    
    analysis = analyze_anomalies(df_all)
    print("\nAnálise de Anomalias (Location):")
    print(json.dumps(analysis, indent=2, default=str))
    
    print(f"\nProcesso concluído. Resultados em: {output_path}")

if __name__ == "__main__":
    main()
