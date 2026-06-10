import pandas as pd
import os

def process_real_ga4_csv(raw_file_path, output_path):
    print(f"🚀 Initializing GA4 CSV Processing Pipeline...")
    
    if not os.path.exists(raw_file_path):
        print(f"❌ Error: Cannot find raw file at {raw_file_path}")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"📦 Loading raw BigQuery export table from: {raw_file_path}")
    df = pd.read_csv(raw_file_path)
    
    print(f"🧼 Cleaning missing fields and obfuscated strings...")
    if "traffic_source_medium" in df.columns:
        df["traffic_source_medium"] = df["traffic_source_medium"].fillna("direct")
        df["traffic_source_medium"] = df["traffic_source_medium"].replace("(data deleted)", "direct")
    else:
        df["traffic_source_medium"] = "direct"
        
    df["device_category"] = df["device_category"].fillna("desktop")
    df["geo_country"] = df["geo_country"].fillna("Unknown")
    df["page_location"] = df["page_location"].fillna("/")
    
    print(f"⚙️ Engineering explicit binary funnel matrix stages...")
    df["stage_1_session_start"] = (df["event_name"] == "session_start").astype(int)
    df["stage_2_view_item"] = (df["event_name"] == "view_item").astype(int)
    df["stage_3_add_to_cart"] = (df["event_name"] == "add_to_cart").astype(int)
    df["stage_4_begin_checkout"] = (df["event_name"] == "begin_checkout").astype(int)
    df["stage_5_purchase"] = (df["event_name"] == "purchase").astype(int)
    
    print(f"🔬 Engineering deterministic A/B testing variants...")
    df["exp_group"] = df["user_pseudo_id"].astype(str).apply(
        lambda x: "Variant" if hash(x) % 2 == 0 else "Control"
    )
    
    df.to_csv(output_path, index=False)
    print(f"✅ Success! Transformed and saved {len(df)} rows to: {output_path}")

if __name__ == "__main__":
    # Dynamically find the absolute path of the directory containing this script
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    RAW_INPUT = os.path.join(BASE_DIR, "data", "raw", "ga4_events_dump.csv")
    TRANSFORMED_OUTPUT = os.path.join(BASE_DIR, "data", "transformed", "flattened_events.csv")
    
    process_real_ga4_csv(RAW_INPUT, TRANSFORMED_OUTPUT)