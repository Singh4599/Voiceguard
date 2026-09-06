import sys
import os
import pickle
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.ai.feature_extractor import extract_features
import numpy as np

f1 = "/Users/dhruvsingh/Downloads/ElevenLabs_2026-09-04T06_55_37_Bunty – Reel Perfect Voice_pvc_sp100_s50_sb75_se0_b_m2 (1).wav"
f2 = "/Users/dhruvsingh/Downloads/ElevenLabs_2026-09-04T08_40_51_Kanika - Warm, Expressive and Natural_pvc_sp100_s50_sb75_se0_m2.wav"
f3 = "/Users/dhruvsingh/Desktop/Voiceguard/backend/training_data/real/exotel_real_call_12f176d1786b9bde19afcf9f1b941a94_chunk_0014.wav"
f4 = "/Users/dhruvsingh/Desktop/Voiceguard/backend/training_data/real/exotel_real_call_12f176d1786b9bde19afcf9f1b941a94_chunk_0032.wav"

with open("models/scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

for name, f in [("Kanika (AI)", f2), ("Human 1", f3)]:
    with open(f, "rb") as fh:
        data = fh.read()
    feats = extract_features(data)
    feats_scaled = scaler.transform(feats.reshape(1, -1))[0]
    print(f"\n--- {name} ---")
    print(f"Jitter: {feats_scaled[65]:.4f}")
    print(f"Shimmer: {feats_scaled[66]:.4f}")
    print(f"Voiced Ratio: {feats_scaled[64]:.4f}")
    print(f"F0 Mean: {feats_scaled[61]:.4f}")
    print(f"Spec Entropy: {feats_scaled[57]:.4f}")
    print(f"Spec Flatness: {feats_scaled[58]:.4f}")
    print(f"HNR: {feats_scaled[67]:.4f}")
    print(f"F0 Vel: {feats_scaled[68]:.4f}")
    print(f"RMS Var: {feats_scaled[79]:.4f}")
    print(f"Energy Entropy: {feats_scaled[82]:.4f}")
    print(f"MFCC Var (mean): {np.mean(feats_scaled[13:26]):.4f}")

