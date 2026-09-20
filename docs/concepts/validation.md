# VALIDATION EVIDENCE

> Phase 2 完整驗證證據表。核心結論：**Historical statistical signal does NOT imply executable trading edge。**

## 總表

| Phase | Target | Sample | Method | Result | Interpretation |
|-------|--------|--------|--------|--------|----------------|
| 2V-A | Real providers + OSE + TW | 18 providers, real network | 真實 E2E 驗證 | 9 provider OK, real model inference | Pipeline 真實可跑（非 unit test） |
| 2V-B | Proxy ^N225 | ~1090 origins | walk-forward OOS | 全模型 MASE ≥ 1.0 | NO_EVIDENCE（proxy 無預測結構） |
| 2V-B.3 | Direct Micro bar | 960 days / ~831 origins | walk-forward OOS | VAR MASE 0.958, dir 62.2%, MCC 0.241（顯著） | STATISTICAL_FORECAST_EVIDENCE |
| 2V-C | VAR strategy | 831 trades | cost stress (C0-C3) | -259 pts/trade, 32% win | NO_ECONOMIC_EDGE |
| 2V-C.1 | Gap causality | 831 origins | pre-close vs full-close | gap edge 85.2% but non-causal; pre-close 41.3% | NON_EXECUTABLE_FORECAST_EDGE |
| 2V-D | Forward Shadow | infra | registry + activation | infra ready, evidence NONE_YET | forward evidence 未累積 |
| 2V-E | Daily operations | infra | ingest + cycle | manual ingest + daily cycle ready | operational workflow ready |

## 關鍵因果發現（2V-C.1）

```
R_CC = R_GAP + R_OC（close-to-close = gap + intraday）

corr(VAR forecast, gap)  = +0.726（sign）/ +0.896（return）
corr(r_t, gap)           = -0.919（當日 return 與 gap 強烈反向 = mean reversion）
corr(VAR forecast, intraday) = -0.378（intraday 反向）

→ VAR 的 edge 85.2% 在 gap
→ 但 gap edge 需要「當日完整 return r_t」，r_t 只在 close 才知道 = gap 開始時刻
→ full-close signal 85.2% gap 準確（non-causal）
→ pre-close signal（r_{t-1}）崩潰到 41.3%（比隨機差）
```

## 結論

| 項 | 值 |
|----|-----|
| Proxy OOS | NO_EVIDENCE |
| Direct Micro forecast | STATISTICAL_FORECAST_EVIDENCE（非可執行） |
| Executability | NON_EXECUTABLE_FORECAST_EDGE |
| Strategy | NO_ECONOMIC_EDGE |
| Forward | NONE_YET / EVIDENCE_ACCUMULATING |
| Strategy candidate | NONE |
| Production candidate | NONE |

**VAR(1) 有真實統計 forecast edge（MASE 0.958, direction 62.2%），但本質上 non-causal / non-executable，無法轉成交易決策。**
