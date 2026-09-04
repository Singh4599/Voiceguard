"""
app/ai/training/train.py — Train the voice cloning detection model.

Steps:
1. Load WAV files from training_data/real/ and training_data/fake/
2. Extract 62-dim feature vectors (feature_extractor.py)
3. Train RandomForestClassifier + MLPClassifier
4. Save best model + scaler to models/

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

# Adjust sys.path so we can import app.*
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


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("VoiceGuard — Voice Cloning Detector Training")
    logger.info("=" * 60)

    # ── 1. Load data ──────────────────────────────────────────────────────
    X, y = _load_dataset()
    if len(X) < 10:
        logger.error(
            "Not enough data (%d samples). Run generate_data.py first.", len(X)
        )
        return

    logger.info("Dataset: %d samples | %d real | %d fake",
                len(y), int((y == 0).sum()), int((y == 1).sum()))

    # ── 2. Split ──────────────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── 3. Scale ──────────────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # ── 4. Train multiple models, pick best ───────────────────────────────
    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200, max_depth=15, min_samples_leaf=2,
            class_weight="balanced", random_state=42, n_jobs=-1
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.05,
            random_state=42
        ),
        "NeuralNetwork": MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation="relu",
            max_iter=500,
            random_state=42,
            early_stopping=True,
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

        # 5-fold CV
        cv_scores = cross_val_score(model, X_train_s, y_train,
                                     cv=5, scoring="roc_auc")

        logger.info(
            "%-20s  Acc=%.2f%%  AUC=%.3f  CV-AUC=%.3f±%.3f  (%.1fs)",
            name, acc * 100, auc, cv_scores.mean(), cv_scores.std(), dt
        )
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

    # ── 5. Save best model ────────────────────────────────────────────────
    logger.info("\n✅ Best model: %s  (AUC=%.3f)", best_name, best_auc)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(best_model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    # ── 6. Write report ───────────────────────────────────────────────────
    report_lines = [
        "VoiceGuard — Voice Cloning Detection Model Training Report",
        "=" * 60,
        f"Best Model    : {best_name}",
        f"Best AUC      : {best_auc:.4f}",
        f"Training Samples : {len(X_train)}",
        f"Test Samples  : {len(X_test)}",
        "",
    ]
    for name, r in results.items():
        report_lines += [
            f"\n{'─'*40}",
            f"Model: {name}",
            f"Accuracy : {r['accuracy']:.4f}",
            f"AUC      : {r['auc']:.4f}",
            f"CV AUC   : {r['cv_mean']:.4f} ± {r['cv_std']:.4f}",
            f"\nClassification Report:\n{r['report']}",
            f"Confusion Matrix: {r['confusion']}",
        ]
    REPORT_PATH.write_text("\n".join(report_lines))

    logger.info("Model saved  → %s", MODEL_PATH)
    logger.info("Scaler saved → %s", SCALER_PATH)
    logger.info("Report saved → %s", REPORT_PATH)
    logger.info("\n🎯 Training complete! Restart uvicorn to load the new model.")


def _load_dataset():
    """Load all WAV files from training_data/ and extract features."""
    X, y = [], []
    real_dir = TRAINING_DIR / "real"
    fake_dir = TRAINING_DIR / "fake"

    for label, directory in [(0, real_dir), (1, fake_dir)]:
        cls_name = "real" if label == 0 else "ai_clone"
        wav_files = list(directory.glob("*.wav"))
        logger.info("Loading %d %s samples...", len(wav_files), cls_name)

        for wav_path in wav_files:
            try:
                wav_bytes = wav_path.read_bytes()
                features = extract_features(wav_bytes)
                if features is not None:
                    X.append(features)
                    y.append(label)
            except Exception as exc:
                logger.warning("Skipping %s: %s", wav_path.name, exc)

    return np.array(X), np.array(y)


if __name__ == "__main__":
    main()
