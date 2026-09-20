"""Phase 2G — Dynamic weight method（M）。簡單、可解釋、deterministic、versioned。

權重不得由 DeepSeek / Cherry Studio / LLM 決定，只能由程式計算。

公式（weight_method_version = v1）：
  w_raw(model) = inv_loss * calibration_factor * reliability_factor * sample_shrinkage
  inv_loss          = 1 / (loss + eps)          （loss 越低權重越高）
  calibration_factor = 1 - min(calibration_error, 1)
  reliability_factor = 1 - failure_rate
  sample_shrinkage   = n / (n + shrinkage_k)     （小樣本往 0 縮，shrinkage to global）
  最後 normalize 使權重和 = 1。
"""
from __future__ import annotations

WEIGHT_METHOD_VERSION = "v1"
EPS = 1e-9


def compute_weights(model_stats: list[dict], shrinkage_k: float = 20.0,
                    method_version: str = WEIGHT_METHOD_VERSION) -> dict[str, float]:
    """model_stats: list of {model, loss, calibration_error, failure_rate, sample_size}.

    回傳 deterministic、normalized 權重 dict。loss 為 None → 跳過該模型。
    """
    raw: dict[str, float] = {}
    for s in model_stats:
        m = s.get("model")
        loss = s.get("loss")
        if m is None or loss is None:
            continue
        n = s.get("sample_size") or 0
        calib = s.get("calibration_error") or 0.0
        fail = s.get("failure_rate") or 0.0
        inv_loss = 1.0 / (max(float(loss), 1e-6) + EPS)
        calib_factor = 1.0 - min(max(float(calib), 0.0), 1.0)
        reliability_factor = 1.0 - min(max(float(fail), 0.0), 1.0)
        shrinkage = n / (n + shrinkage_k) if n > 0 else 0.0
        raw[m] = inv_loss * calib_factor * reliability_factor * shrinkage
    total = sum(raw.values())
    if total <= 0:
        return {m: 1.0 / len(raw) for m in raw} if raw else {}
    return {m: v / total for m, v in raw.items()}
