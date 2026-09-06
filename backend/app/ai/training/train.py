"""
app/ai/training/train.py — Train the voice cloning detection model.

UPGRADED: Ensemble model (RF + GBM + MLP) for much higher real-world accuracy.

Run:
    cd backend
    python -m app.ai.training.download_data    # download real AI voice datasets
    python -m app.ai.training.generate_data    # generate synthetic data
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
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
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


def _build_ensemble(n_features: int):
    """
    Build a VotingClassifier ensemble:
    - RandomForest: good at non-linear boundaries, robust to noise
    - GradientBoosting: sequentially corrects errors, great for tabular
    - MLP: captures complex interactions between features

    All three vote (soft voting = probability average) → more robust than any single model.
    """
    rf = RandomForestClassifier(
        n_estimators=500,
        max_depth=25,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    gbm = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_samples_leaf=4,
        subsample=0.8,
        max_features="sqrt",
        random_state=42,
    )

    mlp = MLPClassifier(
        hidden_layer_sizes=(256, 128, 64),
        activation="relu",
        solver="adam",
        alpha=0.001,          # L2 regularization
        batch_size=256,
        learning_rate="adaptive",
        max_iter=300,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=42,
    )

    ensemble = VotingClassifier(
        estimators=[
            ("rf", rf),
            ("gbm", gbm),
            ("mlp", mlp),
        ],
        voting="soft",          # Average probabilities
        weights=[3, 2, 2],      # RF gets extra weight (most interpretable + robust)
    )

    return ensemble


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("VoiceGuard — Voice Cloning Detector Training (ENSEMBLE)")
    logger.info("=" * 60)
    logger.info("CPU cores: %d  |  Workers: %d", mp.cpu_count(), N_WORKERS)

    X, y = _load_dataset_parallel()
    if len(X) < 10:
        logger.error("Not enough data (%d samples). Run generate_data.py first.", len(X))
        return

    logger.info("Dataset: %d total | %d real | %d fake",
                len(y), int((y == 0).sum()), int((y == 1).sum()))
    logger.info("Feature dimensions: %d", X.shape[1])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # ── Train ensemble ────────────────────────────────────────────────────
    logger.info("Training ensemble (RF + GBM + MLP)...")
    t0 = time.time()
    ensemble = _build_ensemble(X.shape[1])
    ensemble.fit(X_train_s, y_train)
    dt = time.time() - t0
    logger.info("Ensemble training done in %.1fs", dt)

    y_pred  = ensemble.predict(X_test_s)
    y_proba = ensemble.predict_proba(X_test_s)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)

    logger.info("Ensemble  Acc=%.2f%%  AUC=%.4f", acc * 100, auc)

    # ── 5-fold CV on training set ─────────────────────────────────────────
    logger.info("Running 5-fold cross-validation...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(ensemble, X_train_s, y_train,
                                cv=cv, scoring="roc_auc", n_jobs=-1)
    logger.info("CV-AUC: %.4f ± %.4f", cv_scores.mean(), cv_scores.std())

    report = classification_report(y_test, y_pred,
                                   target_names=["real", "ai_clone"])
    cm = confusion_matrix(y_test, y_pred).tolist()

    logger.info("\n%s", report)
    logger.info("Confusion Matrix: %s", cm)

    # ── Save ──────────────────────────────────────────────────────────────
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(ensemble, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    report_lines = [
        "VoiceGuard — Voice Cloning Detection Model Training Report",
        "=" * 60,
        f"Model         : Ensemble (RandomForest + GradientBoosting + MLP)",
        f"Feature dims  : {X.shape[1]}",
        f"Accuracy      : {acc:.4f}",
        f"AUC           : {auc:.4f}",
        f"CV-AUC        : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}",
        f"Total Samples : {len(X)}",
        f"Train Samples : {len(X_train)}",
        f"Test Samples  : {len(X_test)}",
        f"Train time    : {dt:.1f}s",
        "",
        "Classification Report:",
        report,
        f"Confusion Matrix: {cm}",
    ]
    REPORT_PATH.write_text("\n".join(report_lines))

    logger.info("Model saved  -> %s", MODEL_PATH)
    logger.info("Scaler saved -> %s", SCALER_PATH)
    logger.info("Report saved -> %s", REPORT_PATH)
    logger.info("\nTraining complete! Restart uvicorn to load the new model.")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
