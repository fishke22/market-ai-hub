# MODEL LICENSE MATRIX（模型授權矩陣）

Phase 2D 盤點的模型授權。**code license 與 weight license 分開**；weights 一律不入 Git。

| 模型 | Code License | Weight License | 商用 | 公開再散布 | 目前用途 | 目前狀態 |
|------|--------------|----------------|------|-----------|----------|----------|
| Chronos-2 | Apache-2.0 | Apache-2.0 | ✅ | ✅（本專案仍不散布） | 價格預測（V1） | AVAILABLE |
| TimesFM-3.0 | Apache-2.0 | **timesfm-non-commercial-license-v1.0** | ❌ | ❌ | 價格預測（V1，research only） | AVAILABLE |
| XGBoost | Apache-2.0 | n/a（無 pretrained） | ✅ | n/a | 方向分類 | AVAILABLE |
| LightGBM | MIT | n/a | ✅ | n/a | 方向分類 | AVAILABLE |
| FinCast | Apache-2.0（repo） | research/education | ❌ | ❌ | 價格（bridge，point only） | PARTIAL |
| Kronos-TW | registry: MIT | model card: MIT | 依完整授權 | 不打包權重 | 台股價格 challenger | CHALLENGER；未因授權描述啟用 |
| Sundial | registry: Apache-2.0 | model card: Apache-2.0 | 依完整授權 | 不打包權重 | 價格 challenger | adapter/runtime 另驗，不再稱 UNKNOWN/gated |
| TinyTimeMixer (TTM) | Apache-2.0 | Apache-2.0 | ✅ | ✅ | 價格 challenger | CHALLENGER |
| NHITS / NBEATSx | Apache-2.0 | n/a（fit-on-the-fly） | ✅ | n/a | 價格 challenger | CHALLENGER |
| Moirai-2 | Apache-2.0（uni2ts） | **NONCOMMERCIAL** | ❌ | ❌ | 價格 challenger | NONCOMMERCIAL；runtime 另驗 |

## 重要

- **TimesFM-3.0 weights 為非商業授權**：禁止商業部署、禁止再散布。所有輸出帶 `TIMESFM3_NON_COMMERCIAL_ONLY`。
- 2026-09-24 公開 model card 可讀：Sundial 標 Apache-2.0，Kronos-TW 標 MIT，Moirai-2 標 CC-BY-NC-4.0。頁面可讀不等於本機完成下載/授權驗收；不再以舊 gated 描述推論 runtime 狀態。
- **FinCast**：repo Apache-2.0，但官方 README 標 research/education。
- **NONCOMMERCIAL_RESEARCH_ONLY** 的權重：允許個人研究使用，但不得放入公開 GitHub model files、不得再散布、
  不得誤寫成 Apache weight license。

## 硬體限制

RTX 4060 Ti **16GB** 為本機上限。禁止為硬跑模型造成長時間 OOM / swap；OOM → `BLOCKED_HARDWARE`。

模型估計 VRAM 見 `config/model_registry.yaml`（`estimated_vram_mb` 欄位）。

## 2026-09-24 primary model-card check

- [Sundial](https://huggingface.co/thuml/sundial-base-128m)
- [Kronos-TW](https://huggingface.co/talant28/Kronos-TW-Predictor)
- [Moirai-2](https://huggingface.co/Salesforce/moirai-2.0-R-small)

Model-card metadata is evidence of the publisher's stated license, not a complete legal
clearance of tokenizer/base weights/training data. Pin the exact revision and license text
before download or deployment. Repository policy keeps ALL weights out of Git even when
an upstream license permits some redistribution; this policy is not the license itself.
