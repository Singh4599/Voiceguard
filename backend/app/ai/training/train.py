"""
app/ai/training/train.py — Train the voice cloning detection model.

FAST version: uses multiprocessing to extract features in parallel.
50,000 samples → ~4 minutes (vs 33 min single-threaded).

Run:
    cd backend
    python -m app.ai.training.generate_data   # generate training data first
    python -m app.ai.training.train

Output:
    backend/models/voice_clone_detector.pkl
    backend/models/scaler.pkl
    backend/models/training_report.txt
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import pickle
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, roc_auc_score
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.ai.feature_extractor import extract_features

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")

TRAINING_DIR = Path(__file__).parent.parent.parent.parent / "training_data"
MODEL_DIR    = Path(__file__).parent.parent.parent.parent / "models"
MODEL_PATH   = MODEL_DIR / "voice_clone_detector.pkl"
SCALER_PATH  = MODEL_DIR / "scaler.pkl"
REPORT_PATH  = MODEL_DIR / "training_report.txt"

# Use all available CPU cores for parallel feature extraction
N_WORKERS = max(1, mp.cpu_count() - 1)


def _extract_one(wav_path: Path):
    """Worker function: extract features from one WAV file."""
    try:
        wav_bytes = wav_path.read_bytes()
        return extract_features(wav_bytes)
    except Exception:
        return None


def _load_class_parallel(directory: Path, label: int, cls_name: str):
    """Load all WAV files in directory using multiprocessing pool."""
    wav_files = list(directory.glob("*.wav"))
    logger.info("Loading %d %s samples using %d workers...",
                len(wav_files), cls_name, N_WORKERS)

    t0 = time.time()
    chunk_size = max(1, len(wav_files) // (N_WORKERS * 4))

    with mp.Pool(processes=N_WORKERS) as pool:
        results = pool.map(_extract_one, wav_files, chunksize=chunk_size)

    X, y = [], []
    skipped = 0
    for features in results:
        if features is not None:
            X.append(features)
            y.append(label)
        else:
            skipped += 1

    dt = time.time() - t0
    logger.info("  Done: %d features, %d skipped  (%.1fs @ %.0f samples/s)",
                len(X), skipped, dt, len(X) / max(dt, 0.001))
    return X, y


def _load_dataset_parallel():
    """Load all WAV files from training_data/ in parallel."""
    real_dir = TRAINING_DIR / "real"
    fake_dir = TRAINING_DIR / "fake"

    X_real, y_real = _load_class_parallel(real_dir, 0, "real")
    X_fake, y_fake = _load_class_parallel(fake_dir, 1, "ai_clone")

    X = np.array(X_real + X_fake)
    y = np.array(y_real + y_fake)
    return X, y


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("VoiceGuard — Voice Cloning Detector Training (PARALLEL)")
    logger.info("=" * 60)
    logger.info("CPU cores: %d  |  Workers: %d", mp.cpu_count(), N_WORKERS)

    X, y = _load_dataset_parallel()
    if len(X) < 10:
        logger.error("Not enough data (%d samples). Run generate_data.py first.", len(X))
        return

    logger.info("Dataset: %d total | %d real | %d fake",
                len(y), int((y == 0).sum()), int((y == 1).sum()))

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=300, max_depth=20, min_samples_leaf=2,
            class_weight="balanced", random_state=42, n_jobs=-1
        ),
    }

    best_name, best_model, best_auc = None, None, 0.0
    results = {}

    for name, model in models.items():
        t0 = time.time()
        model.fit(X_train_s, y_train)
        dt = time.time() - t0

        y_pred  = model.predict(X_test_s)
        y_proba = model.predict_proba(X_test_s)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_proba)
        cv_scores = cross_val_score(model, X_train_s, y_train, cv=5, scoring="roc_auc")

        logger.info("%-20s  Acc=%.2f%%  AUC=%.3f  CV-AUC=%.3f±%.3f  (%.1fs)",
                    name, acc * 100, auc, cv_scores.mean(), cv_scores.std(), dt)

        results[name] = {
            "accuracy": acc, "auc": auc,
            "cv_mean": cv_scores.mean(), "cv_std": cv_scores.std(),
            "report": classification_report(y_test, y_pred,
                                            target_names=["real", "ai_clone"]),
            "confusion": confusion_matrix(y_test, y_pred).tolist(),
        }

        if auc > best_auc:
            best_auc = auc
            best_model = model
            best_name = name

    logger.info("\n✅ Best model: %s  (AUC=%.3f)", best_name, best_auc)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(best_model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    report_lines = [
        "VoiceGuard — Voice Cloning Detection Model Training Report",
        "=" * 60,
        f"Best Model    : {best_name}",
        f"Best AUC      : {best_auc:.4f}",
        f"Total Samples : {len(X)}",
        f"Train Samples : {len(X_train)}",
        f"Test Samples  : {len(X_test)}",
        "",
    ]
    for name, r in results.items():
        report_lines += [
            f"\n{'─'*40}", f"Model: {name}",
            f"Accuracy : {r['accuracy']:.4f}", f"AUC      : {r['auc']:.4f}",
            f"CV AUC   : {r['cv_mean']:.4f} ± {r['cv_std']:.4f}",
            f"\nClassification Report:\n{r['report']}",
            f"Confusion Matrix: {r['confusion']}",
        ]
    REPORT_PATH.write_text("\n".join(report_lines))

    logger.info("Model saved  → %s", MODEL_PATH)
    logger.info("Scaler saved → %s", SCALER_PATH)
    logger.info("Report saved → %s", REPORT_PATH)
    logger.info("\n🎯 Training complete! Restart uvicorn to load the new model.")


if __name__ == "__main__":
    # Required for multiprocessing on macOS (spawn start method)
    mp.set_start_method("spawn", force=True)
    main()
