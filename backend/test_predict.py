import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.ai.cloning_detector import CloningDetector
from app.ai.feature_extractor import extract_features

f1 = "/Users/dhruvsingh/Downloads/ElevenLabs_2026-09-04T06_55_37_Bunty – Reel Perfect Voice_pvc_sp100_s50_sb75_se0_b_m2 (1).wav"
f2 = "/Users/dhruvsingh/Downloads/ElevenLabs_2026-09-04T08_40_51_Kanika - Warm, Expressive and Natural_pvc_sp100_s50_sb75_se0_m2.wav"
f3 = "/Users/dhruvsingh/Desktop/Voiceguard/backend/training_data/real/exotel_real_call_12f176d1786b9bde19afcf9f1b941a94_chunk_0014.wav"
f4 = "/Users/dhruvsingh/Desktop/Voiceguard/backend/training_data/real/exotel_real_call_12f176d1786b9bde19afcf9f1b941a94_chunk_0032.wav"

detector = CloningDetector()
detector.load()

for name, f in [("Bunty (AI)", f1), ("Kanika (AI)", f2), ("Human 1", f3), ("Human 2", f4)]:
    with open(f, "rb") as fh:
        data = fh.read()
    res = detector.predict(data)
    print(f"\n--- {name} ---")
    print(f"Confidence: {res.confidence:.4f} | is_clone: {res.is_clone}")
    print(f"Indicators: {res.top_indicators}")
    print(f"Raw scores: {res.raw_scores}")
    feats = extract_features(data)
    print(f"Raw Spec Entropy (features[57]): {feats[57]:.4f}")
