import os
import numpy as np
import pandas as pd
from scipy.stats import norm

class ExperimentSimulator:
    def __init__(self, data_path="data/transformed/flattened_events.csv", output_dir="data/models/"):
        self.data_path = data_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def load_and_segment_data(self):
        """Loads the real transformed GA4 dataset processed by event_parser.py."""
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(
                f"❌ Transformed data not found at {self.data_path}. "
                f"Please run 'python src/event_parser.py' first to initialize the file!"
            )
        
        print(f"📦 Loading transformed behavioral analytics data from: {self.data_path}")
        df = pd.read_csv(self.data_path)
        return df

    def run_z_test(self, successes_control, total_control, successes_variant, total_variant):
        """Performs a two-proportion Z-test for conversion differences."""
        p_control = successes_control / total_control if total_control > 0 else 0
        p_variant = successes_variant / total_variant if total_variant > 0 else 0
        
        if total_control == 0 or total_variant == 0:
            return 0.0, 1.0, 0.0
        
        # Pooled conversion rate
        p_pooled = (successes_control + successes_variant) / (total_control + total_variant)
        
        # Standard error
        se = np.sqrt(p_pooled * (1 - p_pooled) * (1 / total_control + 1 / total_variant))
        
        if se == 0:
            return 0.0, 1.0, 0.0
        
        # Z-score and two-tailed p-value
        z_score = (p_variant - p_control) / se
        p_value = 2 * (1 - norm.cdf(abs(z_score)))
        
        # Relative Lift
        lift = ((p_variant - p_control) / p_control) * 100 if p_control > 0 else 0
        
        return float(z_score), float(p_value), float(lift)

    def analyze_funnel_experiment(self):
        """Computes statistical metrics across all critical checkout drop-off gates."""
        df = self.load_and_segment_data()
        
        # Explicit mapping matching your true transformed layout columns exactly
        stages = [
            ("Session -> View", "stage_1_session_start", "stage_2_view_item"),
            ("View -> Cart", "stage_2_view_item", "stage_3_add_to_cart"),
            ("Cart -> Checkout", "stage_3_add_to_cart", "stage_4_begin_checkout"),
            ("Checkout -> Purchase", "stage_4_begin_checkout", "stage_5_purchase"),
            ("Macro Funnel (Session -> Purchase)", "stage_1_session_start", "stage_5_purchase")
        ]
        
        results = []
        
        # Isolate cohorts using the exp_group generated during parsing
        control_df = df[df["exp_group"] == "Control"]
        variant_df = df[df["exp_group"] == "Variant"]
        
        print(f"📊 Running hypothesis engines across {len(control_df)} Control vs {len(variant_df)} Variant interactions...")

        for stage_name, base_stage, target_stage in stages:
            # Aggregate totals dynamically from binary flags
            n_control = int(control_df[base_stage].sum())
            x_control = int(control_df[target_stage].sum())
            
            n_variant = int(variant_df[base_stage].sum())
            x_variant = int(variant_df[target_stage].sum())
            
            z_stat, p_val, lift_pct = self.run_z_test(x_control, n_control, x_variant, n_variant)
            
            results.append({
                "Funnel_Conversion_Step": stage_name,
                "Control_Base_Volume": n_control,
                "Control_Conversions": x_control,
                "Control_CR_Pct": round((x_control / n_control) * 100, 2) if n_control > 0 else 0,
                "Variant_Base_Volume": n_variant,
                "Variant_Conversions": x_variant,
                "Variant_CR_Pct": round((x_variant / n_variant) * 100, 2) if n_variant > 0 else 0,
                "Relative_Lift_Pct": round(lift_pct, 2),
                "Z_Score": round(z_stat, 3),
                "P_Value": round(p_val, 5),
                "Statistical_Significance": "SIGNIFICANT" if p_val < 0.05 else "INSIGNIFICANT"
            })
            
        results_df = pd.DataFrame(results)
        
        # Save structural model output matrix for UI visualizations
        output_file = os.path.join(self.output_dir, "experiment_results.csv")
        results_df.to_csv(output_file, index=False)
        print(f"\n✅ Experiment calculations complete. Matrix saved to: {output_file}\n")
        print(results_df[["Funnel_Conversion_Step", "Relative_Lift_Pct", "P_Value", "Statistical_Significance"]].to_string(index=False))

if __name__ == "__main__":
    simulator = ExperimentSimulator()
    simulator.analyze_funnel_experiment()