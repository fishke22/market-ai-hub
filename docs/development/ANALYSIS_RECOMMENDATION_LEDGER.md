# ANALYSIS RECOMMENDATION LEDGER — 規格 v1

> 目的：讓「agent 給過的建議」變成可稽核、可對答案、可驅動改進的資料。
> 對應角色：`docs/prompts/FINANCIAL_ANALYST_AGENT_V1.md`（角色 A 的落地機制）。
> 本規格只定義**檔案格式與流程**；不改任何 runtime、不改 evidence gate、不新增 MCP 工具。

## 0. 與既有系統的關係
MARKET_AI_HUB 已有受治理的**預測引擎**（P5 前向、W3.2 契約日結算）與不可變的
PredictionAuditDB。本帳本**不取代**它們，也不重複計算：
- 引擎負責「模型在原點凍結了什麼、答案是什麼」。
- 帳本負責「**agent 對使用者說了什麼**，以及那句話後來對不對」。

兩者以 artifact id 互相引用，永不互相覆寫。

## 1. 檔案位置與格式
- 目錄：`research/analysis_reviews/`
- 帳本：`research/analysis_reviews/recommendations.jsonl`（append-only，一行一筆）
- 檢討：`research/analysis_reviews/reviews.jsonl`（append-only）
- 索引：`research/analysis_reviews/INDEX.md`（人可讀摘要，可重建，非權威）
- 這些檔案屬本地研究產物；**不得**寫入任何帳務、持倉或機密資訊。

## 2. RECOMMENDATION 記錄欄位
```jsonc
{
  "schema": "ANALYSIS_RECOMMENDATION_V1",
  "recommendation_id": "rec-<utc-timestamp>-<short-hash>",
  "created_at": "2026-10-09T12:34:56Z",          // 產生建議的真實時間
  "as_of": "2026-10-09T12:34:56Z",               // 決策原點（資料 cutoff）
  "target": "OSE_NIKKEI225_MICRO_FUTURES",       // 目標實體
  "execution_instrument": "OSE_NIKKEI225_MICRO_FUTURES",
  "horizon": "1d",
  "source_tool": "analyze_jnu",                  // 主要依據的 MCP 工具
  "source_artifacts": ["<prediction_id|evidence_id>"], // 依賴的凍結 artifact
  "data_coverage": {                             // 誠實的涵蓋聲明
    "recorded_window": "2026-10-09T18:55..22:00+08:00",
    "coverage_gap": "其餘時段未錄",
    "freshness": "RECORDED|LIVE|STALE"
  },
  "stance": "NEUTRAL|BULLISH_LEAN|BEARISH_LEAN", // 研究立場
  "strength": "WEAK_UNVALIDATED|MODERATE|STRONG", // 證據強度
  "claim": {                                     // 可機器判定的述句
    "kind": "DIRECTION|THRESHOLD",
    "predicate": "next_settlement > 66140",
    "maturity_at": "2026-10-10T00:00:00Z"
  },
  "invalidation": "依當時 packet 的失效條件原文",
  "evidence_flags": {
    "predictive_gain": false,
    "calibrated": false,
    "trading_edge": false
  },
  "not_trading_advice": true
}
```
- `claim.predicate` 必須是**在寫入當下就能判定真假**的形式（先用官方來源對答案，才可回填 outcome）。
- 若當時證據不足以形成可判定述句，`claim.kind` 填 `NONE`，並在檢討時只檢討 `REASONING_OVERREACH` / `PROCESS_LAPSE`。

## 3. 結算（settle）
- 觸發：`claim.maturity_at` 之後，且有可用的官方對答案來源（與原建議相同的來源類別）。
- 寫入 `reviews.jsonl`，欄位包含：
```jsonc
{
  "schema": "ANALYSIS_REVIEW_V1",
  "review_id": "rev-<utc-timestamp>-<short-hash>",
  "recommendation_id": "rec-...",
  "settled_at": "2026-10-10T00:05:00Z",
  "outcome": "MATCH|MISMATCH|NOT_SETTLABLE",
  "observed": "<官方實際值或狀態>",
  "classification": "DATA_MISS|FEATURE_MISS|MODEL_UNDERPERFORM|REASONING_OVERREACH|PROCESS_LAPSE|NONE",
  "action": "NO_CHANGE|PROMPT_FIX|SOP_FIX|GOVERNED_TICKET",
  "action_ref": "<若有 ticket/PR 則填參照>",
  "notes": "簡短、不誇大"
}
```
- **已結算的建議永不修改**；任何改進都以新版本另記。

## 4. 分類決策樹（避免亂歸因）
1. 原本資料其實不足 / 有漏錄 → `DATA_MISS`。
2. 需要的輸入在原點不可得或 representation 不符 → `FEATURE_MISS`。
3. 資料沒問題、述句也沒誇大，但模型在該原點確實不如基準 → `MODEL_UNDERPERFORM`。
4. 資料/模型都合理，但輸出把弱證據講成成熟訊號 → `REASONING_OVERREACH`。
5. 錯過原點、延遲、漏檢資料狀態 → `PROCESS_LAPSE`。

前 3 類只能走治理流程（`GOVERNED_TICKET`），不得在分析時段偷改；
後 2 類可直接修 prompt / SOP。

## 5. 保證條款
- append-only；不得改寫歷史列。
- 不得為了讓述句成立而修改 `claim`。
- 不得把 `outcome=MATCH` 當成模型已具預測力：單筆命中不是統計證據，
  聚合統計仍以既有評估引擎的樣本門檻為準。
- 帳本不產生任何 probability / edge 主張。
