import pandas as pd
import psycopg2
from psycopg2 import extras
import os

def load_transformed_data_to_postgres(transformed_csv, db_uri):
    print("\n=================== PIPELINE EXECUTION ===================")
    print(f"📂 Reading target CSV file from: {transformed_csv}")
    
    if not os.path.exists(transformed_csv):
        print(f"❌ Error: Cannot find file at {transformed_csv}")
        return

    # Read the file
    df = pd.read_csv(transformed_csv)
    
    # Strip any invisible carriage returns or whitespaces from column headers
    df.columns = df.columns.str.strip().str.replace('\r', '').str.replace('\n', '')
    
    print(f"🔌 Connecting to PostgreSQL container on port 5433...")
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor()
    
    print(f"🧹 Truncating stale warehouse records...")
    cursor.execute("TRUNCATE TABLE raw_ga4_events RESTART IDENTITY;")
    
    insert_query = """
        INSERT INTO raw_ga4_events (
            user_pseudo_id, session_id, event_name, event_timestamp, 
            traffic_source_medium, device_category, geo_country, page_location
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """
    
    # Select the exact columns required by the warehouse schema
    cols_to_load = [
        "user_pseudo_id", "session_id", "event_name", "event_timestamp",
        "traffic_source_medium", "device_category", "geo_country", "page_location"
    ]
    
    warehouse_slice = df[cols_to_load]
    
    print(f"📥 Bulk streaming records into growth_funnel_db...")
    data_tuples = [tuple(x) for x in warehouse_slice.to_numpy()]
    
    try:
        extras.execute_batch(cursor, insert_query, data_tuples, page_size=5000)
        conn.commit()
        print(f"✅ Success! {len(df)} rows successfully committed to PostgreSQL.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Database Insertion Failed: {e}")
    finally:
        cursor.close()
        conn.close()
    print("========================================================\n")

if __name__ == "__main__":
    # Hardcoded local paths anchored to your terminal's verified working directory
    TRANSFORMED_FILE = "data/transformed/flattened_events.csv"
    POSTGRES_URI = "postgresql://postgres:postgres@localhost:5435/growth_funnel_db"
    
    load_transformed_data_to_postgres(TRANSFORMED_FILE, POSTGRES_URI)