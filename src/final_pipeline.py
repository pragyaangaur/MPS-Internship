import pandas as pd
import numpy as np
import json
import os
import matplotlib.pyplot as plt
from scipy.stats import norm

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
DATA_PATH   = '/Users/pragyaangaur/Downloads/My Files/MPS Internship/sunspot-detectives-classifications.csv'
OUTPUT_DIR  = '/Users/pragyaangaur/Downloads/My Files/MPS Internship/Outputs/Final_Run'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Final Selected Parameters
MIN_OVERLAP          = 2
MAX_RELATIVE_SCATTER = 0.5
BIAS_RELIABLE_N      = 20
Z_OUTLIER_THRESHOLD  = 2.5

# ── STEP 1: PARSE DATA ────────────────────────────────────────────────────────
print("1. Loading and parsing dataset...")
cols = ['user_name', 'user_ip', 'annotations', 'subject_data']
df = pd.read_csv(DATA_PATH, usecols=['classification_id'] + cols)
df = df.dropna(subset=['annotations', 'subject_data'])[cols]

def extract_count(annotations):
    try:
        val = json.loads(annotations)[0]['value']
        if isinstance(val, (int, float)): return int(val)
        if isinstance(val, str):
            val = val.strip()
            return int(val) if val else None
        if isinstance(val, list) and val:
            iv = val[0].get('value')
            if isinstance(iv, int): return iv
            lb = val[0].get('label')
            if lb is not None: return int(lb)
    except: return None

def extract_filename(subject_data):
    try:
        fv = list(json.loads(subject_data).values())[0]
        parts = fv['Filename'].replace('.png','').split('_')
        return parts[0], parts[1]
    except: return None, None

def assign_volunteer_id(row):
    if pd.notna(row['user_name']): return row['user_name']
    if pd.notna(row['user_ip']):   return 'anon_' + str(row['user_ip'])
    return 'unknown'

df['spot_count']   = df['annotations'].apply(extract_count)
df = df.dropna(subset=['spot_count'])
df['spot_count']   = df['spot_count'].astype(int)
df[['day_id','group_id']] = df['subject_data'].apply(extract_filename).apply(pd.Series)
df['volunteer_id'] = df.apply(assign_volunteer_id, axis=1)
df = df[df['volunteer_id'] != 'unknown']
df = df.drop(columns=['annotations','subject_data','user_name','user_ip'])
df['day_id_num'] = pd.to_numeric(df['day_id'], errors='coerce')
n_before = len(df)
df = df[df['day_id_num'] < 10000].drop(columns=['day_id_num'])
print(f"   Day-ID cutoff filter: kept {len(df)} / {n_before} rows (day_id < 10000)")

# ── STEP 2: TEOLIXX BENCHMARK CALIBRATION ─────────────────────────────────────
print("2. Calibrating volunteers against benchmark (teolixx)...")
teolixx = df[df['volunteer_id'] == 'teolixx'].copy()
others  = df[df['volunteer_id'] != 'teolixx'].copy()

teolixx_ref = (teolixx.groupby(['day_id','group_id'])['spot_count']
               .median().reset_index()
               .rename(columns={'spot_count':'teolixx_count'}))

merged = pd.merge(others, teolixx_ref, on=['day_id','group_id'])
merged['diff'] = merged['spot_count'] - merged['teolixx_count']

stats = (merged.groupby('volunteer_id')['diff']
         .agg(['mean','std','count']).reset_index()
         .rename(columns={'mean':'bias','std':'scatter','count':'n_overlap'}))
stats['scatter'] = stats['scatter'].fillna(0)

teolixx_mean = (merged.groupby('volunteer_id')['teolixx_count']
                .mean().reset_index()
                .rename(columns={'teolixx_count':'teolixx_mean_count'}))
stats = stats.merge(teolixx_mean, on='volunteer_id')
stats['relative_scatter'] = stats['scatter'] / stats['teolixx_mean_count']

# PLOT: Volunteer Quality Space
plt.figure(figsize=(10, 6))
plt.scatter(stats['n_overlap'], stats['relative_scatter'], alpha=0.5, s=15, c='gray')
plt.axvline(MIN_OVERLAP, color='black', linestyle='--', label=f'Min Overlap = {MIN_OVERLAP}')
plt.axhline(MAX_RELATIVE_SCATTER, color='black', linestyle=':', label=f'Max Rel Scatter = {MAX_RELATIVE_SCATTER}')
# Highlight accepted in green, rejected in red
acc_mask = (stats['n_overlap'] >= MIN_OVERLAP) & (stats['relative_scatter'] <= MAX_RELATIVE_SCATTER)
plt.scatter(stats[acc_mask]['n_overlap'], stats[acc_mask]['relative_scatter'], alpha=0.6, s=15, c='green', label='Accepted')
plt.scatter(stats[~acc_mask]['n_overlap'], stats[~acc_mask]['relative_scatter'], alpha=0.6, s=15, c='red', label='Rejected')
plt.xscale('log')
plt.yscale('log')
plt.xlabel('Number of Images Shared with Teolixx (n_overlap)')
plt.ylabel('Relative Scatter')
plt.title('Volunteer Quality Space')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '01_volunteer_quality_space.png'))
plt.close()

# PLOT: Metrics at low vs high counts
plt.figure(figsize=(8, 6))
plt.scatter(stats['teolixx_mean_count'], stats['relative_scatter'], alpha=0.5, s=15)
plt.xlabel('Mean Teolixx Count on Shared Images')
plt.ylabel('Relative Scatter')
plt.title('Relative Scatter vs True Spot Count')
plt.xscale('log')
plt.yscale('log')
plt.axhline(MAX_RELATIVE_SCATTER, color='red', linestyle='--', label=f'Threshold ({MAX_RELATIVE_SCATTER})')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '02_metrics_low_vs_high_counts.png'))
plt.close()

# ── STEP 3: PARAMETER SENSITIVITY SWEEP ───────────────────────────────────────
print("3. Running Parameter Sensitivity Analysis...")
overlap_grid = [2, 3, 5, 10, 20]
scatter_grid = [0.2, 0.3, 0.5, 0.7, 1.0]
results = np.zeros((len(scatter_grid), len(overlap_grid)))

for i, max_rs in enumerate(scatter_grid):
    for j, min_ov in enumerate(overlap_grid):
        mask = (stats['n_overlap'] >= min_ov) & (stats['relative_scatter'] <= max_rs)
        accepted_count = mask.sum()
        results[i, j] = accepted_count

plt.figure(figsize=(8, 6))
plt.imshow(results, cmap='viridis', origin='lower', aspect='auto')
plt.colorbar(label='Number of Accepted Volunteers')
plt.xticks(range(len(overlap_grid)), overlap_grid)
plt.yticks(range(len(scatter_grid)), scatter_grid)
plt.xlabel('Minimum Overlap Threshold')
plt.ylabel('Maximum Relative Scatter Threshold')
plt.title('Parameter Sensitivity: Accepted Volunteers')
for i in range(len(scatter_grid)):
    for j in range(len(overlap_grid)):
        plt.text(j, i, int(results[i, j]), ha='center', va='center', color='white' if results[i,j] < results.max()/2 else 'black')
# Highlight chosen param
chosen_j = overlap_grid.index(MIN_OVERLAP)
chosen_i = scatter_grid.index(MAX_RELATIVE_SCATTER)
rect = plt.Rectangle((chosen_j - 0.5, chosen_i - 0.5), 1, 1, fill=False, edgecolor='red', linewidth=3)
plt.gca().add_patch(rect)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '03_parameter_sensitivity_heatmap.png'))
plt.close()

# ── STEP 4: OUTLIER REJECTION (WITHIN-GROUP) ──────────────────────────────────

print("4. Performing Within-Group Outlier Rejection...")
accepted_stats = stats[acc_mask].copy()
accepted_ids = accepted_stats['volunteer_id'].tolist() + ['teolixx']
df_work = df[df['volunteer_id'].isin(accepted_ids)].copy()

group_stats = (df_work.groupby(['day_id','group_id'])['spot_count']
               .agg(['mean','std','count']).reset_index()
               .rename(columns={'mean':'group_mean','std':'group_std','count':'n_vol_pre'}))
group_stats['group_std'] = group_stats['group_std'].fillna(0)

df_work = df_work.merge(group_stats[['day_id','group_id','group_mean','group_std']], on=['day_id','group_id'])
df_work['z_score'] = np.where(df_work['group_std'] > 0, (df_work['spot_count'] - df_work['group_mean']) / df_work['group_std'], 0.0)

# PLOT: Z-score distribution vs Gaussian Expectation
plt.figure(figsize=(8, 5))
z_valid = df_work[df_work['group_std'] > 0]['z_score']
plt.hist(z_valid, bins=50, density=True, color='steelblue', alpha=0.7, label='Data Z-scores')
xmin, xmax = plt.xlim()
x = np.linspace(xmin, xmax, 100)
p = norm.pdf(x, 0, 1)
plt.plot(x, p, 'k', linewidth=2, label='Standard Normal')
plt.axvline(Z_OUTLIER_THRESHOLD, color='red', linestyle='--', label=f'Cutoff (+{Z_OUTLIER_THRESHOLD})')
plt.axvline(-Z_OUTLIER_THRESHOLD, color='red', linestyle='--')
plt.xlabel('Z-Score (Deviation from group mean)')
plt.ylabel('Density')
plt.title('Distribution of Individual Count Deviations')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '05_zscore_distribution.png'))
plt.close()

df_work['is_outlier'] = df_work['z_score'].abs() > Z_OUTLIER_THRESHOLD
df_clean = df_work[~df_work['is_outlier']].drop(columns=['group_mean','group_std','z_score','is_outlier'])

# ── STEP 5: FINAL AGGREGATION & STABILITY OUTPUT ──────────────────────────────
print("5. Aggregating to Daily Time Series & Generating Final Output...")
group_counts = (df_clean.groupby(['day_id','group_id'])['spot_count']
                .agg(['mean','std','count']).reset_index()
                .rename(columns={'mean':'mean_count','std':'std_count','count':'n_volunteers'}))
group_counts['std_count'] = group_counts['std_count'].fillna(0)

daily = (group_counts.groupby('day_id')
         .agg(
             daily_count       = ('mean_count', 'sum'),
             daily_uncertainty = ('std_count',  lambda x: np.sqrt((x**2).sum())),
             n_groups          = ('mean_count', 'count'),
             mean_vol_per_group= ('n_volunteers', 'mean')
         ).reset_index())

# PLOT: Final Time Series with Smoothed Stability
plt.figure(figsize=(14, 6))
x_idx = np.arange(len(daily))
plt.plot(x_idx, daily['daily_count'], color='steelblue', alpha=0.5, label='Daily Count', linewidth=0.8)

# Add 180-day smoothed line
smoothed = daily['daily_count'].rolling(window=180, min_periods=1).mean()
plt.plot(x_idx, smoothed, color='darkorange', linewidth=2, label='180-Day Running Mean')

plt.xlabel('Observing Session (Chronological Index)')
plt.ylabel('Daily Sunspot Count')
plt.title(f'Final Calibrated Daily Sunspot Numbers (Overlap≥{MIN_OVERLAP}, Scatter≤{MAX_RELATIVE_SCATTER})')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, '06_final_timeseries.png'))
plt.close()

# ── EXPORT CSVs ───────────────────────────────────────────────────────────────
print("6. Exporting Final Data...")
daily.to_csv(os.path.join(OUTPUT_DIR, 'daily_sunspot_numbers.csv'), index=False)
group_counts.to_csv(os.path.join(OUTPUT_DIR, 'group_sunspot_numbers.csv'), index=False)
accepted_stats.to_csv(os.path.join(OUTPUT_DIR, 'volunteer_stats.csv'), index=False)

print(f"PIPELINE COMPLETE. All rigorous testing plots and final CSVs generated in: {OUTPUT_DIR}")
