# MARKET_AI_HUB vNext：精度與效率優先的修訂設計

日期：2026-09-27。這份設計取代舊 PDF 的施工順序；實際現況以 01 文件與 repository 為準。

## 決策

保留 Hub 為唯一資料身分、預測契約、評估、機率發布與 agent 白話輸出的核心。外部開源工具只做可移除的研究 adapter／獨立實驗。現階段最需要增加的是**可驗證的資訊與簡單基準**，而不是更多大型預測模型或交易平台。

資料 → 可得時間與品質檢查 → 最小特徵集 → baseline／challenger → 凍結預測 → outcome → 評估／校準 → Price/Probability Map → 研究風險情境 → 白話解讀。

主腦只解釋具有 evidence_id 的結果；不自行補機率、修改失效價、把同時相關說成因果、不把研究區域直接當下單指令。底層無法計算就說缺什麼，並提供有依據的條件式觀察方案。

## 模型是否需要新增

| 任務 | 優先方案 | 進場條件 |
|---|---|---|
| 價格基準 | last-price naive、causal drift、moving average | 現有 baseline 保留；全部同 origin／同 target／同樣本比較 |
| 條件式方向／報酬 | regularized linear/logistic 作可解釋 baseline；既有 LightGBM/XGBoost 作 challenger | 先有 PIT cross-market features；一個模型／一組特徵增量，不能無限制搜尋 |
| 波動／尾部 | EWMA + empirical residual block bootstrap；有增益才加 GARCH-t | 使用既有 numpy 先做；估計只用訓練段，保留 skew／fat tail；不強制常態 |
| 價格分位 | 既有 LightGBM quantile objective | 足夠不同 regime 樣本；pinball、coverage、width、crossing 檢查，非只看 MAE |
| 路徑／觸及／先觸及 | 條件 block bootstrap 或可驗證的 stochastic path challenger | 有正確 event labels 與 intraday history；終點分位不能直接推出路徑機率 |
| Regime | 先透明 volatility/trend buckets，再評估 change-point/HMM | bucket 定義只以 train 設定；樣本足夠才增加狀態數 |
| Chronos／TimesFM／其他 foundation | 保留現有兩者 shadow 對照 | 不再為模型數量加入第三個；須證明新增資料／性能增益、權重授權與資源成本 |
| 新聞 | FinGPT 或現有本地 LLM 的結構化事件抽取 | 可驗證 published_at/received_at、來源與人工抽查；FinGPT 不是行情預言機 |
| RL | FinRL-X sandbox，最後才考慮 | 穩定的成本模型、獨立回放 parity、可信 labels、足夠資料；先勝過規則策略 |

沒有任何選型保證提高未來精度。升級以預先登記的樣本外增益、校準、不確定性、延遲與成本共同決定；更複雜但無增益就不採用。

## 跨市場資料契約

候選資訊：JNU、NQ/MNQ、ES、JY、VX、ZF/ZN、美元指數、TMF/TX/MTX、GC、CL。先盤點一個真正有合格歷史資料的 factor，逐個增加，不要求全部供應商先到齊。

每筆至少保留 instrument_id、venue、exact_contract、currency、unit、representation_relation、event_time、session_date、received_at、available_at、source_hash/revision、quality、staleness。feature_available_at 不得早於任一輸入可得時間與實際計算完成時間；historical simulation 的計算延遲假設另標明，不能偽造當年實際接收紀錄。以 origin 對 available_at 做 backward as-of join；只用當時已知修訂，禁止 bfill／nearest future join。

先用 return／lagged return／volatility／relative strength 的小集合；訓練限定 scaling、imputation、z-score、beta／相關窗口。每個 join 輸出 coverage／age／missing reason。NQ 不是 SOX；JY futures 不是 USDJPY spot；ZN 價格不是殖利率；VX futures 不是 VIX cash；代理要標示基差、方向、時區、換月，不自動替代目標。

1m/5m/15m/60m 僅由真實相應頻率資料生成。日清算資料不能上採樣成假盤中；只有 callback 不能宣稱多年連續歷史。缺價保持缺值，不能默認報酬 0。盤中與日清算為不同任務，分開評估。

## Price Map + Probability Map

- Price Map：中心、Buy/Neutral/Profit Zone、Breakout、Breakdown、Model Failure。名稱是條件式研究區域；不是個人化進出場推薦。
- Probability Map：分開 terminal zone、touch upper/lower、upper-before-lower、neither、ambiguous/censored。terminal 的互斥分區才應加總 1；上下 touch 可同時發生，不能硬加總 1。
- First passage 要有路徑順序。日 OHLC 同日雙邊觸及仍是 ambiguous；不能猜先後。缺資料／到期／觀察結束的 censoring 規則預先固定。
- 區域 threshold 使用 origin 可得 ATR／sigma 距離與固定規則，不綁定某次 68,000 價格。生成 threshold 與驗證 outcome 分離，不可用未來高低改 barrier。
- raw score、uncalibrated probability、calibrated probability 分欄；未知 probability 用 null + reason，不以 0 或 confidence=0.8 代填。
- 最終輸出：目前位於哪裡、可計算的情境、風險尾部、失效條件、資料新鮮度、證據等級。沒有合格機率就給條件式區域說明，不杜撰「七成」。
- R/R 幾何比例不等於 expected value。期望值須有路徑機率、止盈止損先後、成本、跳空滑價；不把 terminal map 直接套 stop-first 策略。

## 可信度驗收

1. 凍結 prediction／target／horizon／event-family／model revision／feature snapshot／protocol，再收 outcome。來源修訂追加版本，不改寫舊預測。
2. 時間序列 walk-forward；training、calibration、validation、final 分離。重疊 labels 要 purge/embargo；所有調參與特徵挑選只在 train/validation。final 使用次數寫入帳本，失敗也不能清除痕跡。
3. 本次舊 48 final 已曝光且有 horizon 問題；修復後不要重跑並自稱全新 final。建立新 preregistered protocol／新的未來觀察區段。
4. 價格 MAE/RMSE/MASE + direction + pinball／coverage／width；probability 用 Brier/log loss/reliability bins，加分市場／regime／horizon 切片。ECE 與 Brier 不單獨證明 calibration；樣本與 bin 不確定性必須顯示。
5. 同 origins paired block bootstrap，依 label overlap／序列依賴選合理 block；多模型搜尋需保留 experiment ledger，防止挑最好一次。不得把 overlapping windows 當獨立樣本倍增 n。
6. 分開工程可跑、資料可用、真實 forward、校準通過、樣本外預測增益、含成本經濟增益。50/50/50 僅沿用當前門檻，不任意為過關下修。
7. Champion/challenger 分任務，不是單一「最強模型」。簡單平均只作 baseline；加權／stacking 只在獨立 train/validation 學習，監測模型相關性、drift、失效與 abstain。沒有增益保持 baseline。

## 開源工具取捨

| 工具 | 決定 | 實際用途與限制 |
|---|---|---|
| Qlib | 後續優先研究 adapter，獨立環境 | 借用 data handler／experiment flow；不替換 Hub PIT/audit。上游目前 mlflow<3.13，Hub research extra 3.16.1 不可直接共裝 |
| FinGPT | 事件特徵實驗，晚於基本跨市場特徵 | 先現有本地模型；code license 不代表所有 base weights／news license；付費API非必要依賴 |
| FinRobot | 只借鑑分析工作流 | 主腦已有角色，不再疊 agent 平台；不把 LLM consensus 當統計證據 |
| FinRL-X | 延後獨立 sandbox | weight-centric 股票組合設計不能原封套槓桿期貨；預設 broker integration 不啟動 |
| LEAN | 第二引擎候選，先做離線最小 parity | engine 開源不等於 LEAN CLI 免費；官方 CLI 要付費組織，不納入免費必需路徑；用開源 engine 原始碼或放棄此候選 |
| NautilusTrader | 與 LEAN 擇一先做 parity；未來 paper 候選 | v2 文件目前 RC、官方不建議實盤資金；固定 stable 版本並用對應文檔，不直接安裝 main/--pre |
| vn.py | 參考／備選 | 不再引入第二套 GUI、行情與帳號生命週期；只有明確 adapter 需求才接 |
| FreqAI | 借鑑 retrain／drift／walk-forward 模式 | 主要 crypto workflow，example 不適合 production；GPL 授權界線另查，不直接搬核心程式進 Hub |
| Jerry／來源不明工具 | 暫不納入 | proposal 未給可確證 repository/license；不猜連結、不複製未授權碼 |
| MLflow／OTel／Prometheus／Grafana | 按需要啟用 | 先既有 experiment ledger／本機報表；有多模型 artifact 追蹤需求才 MLflow，不一次加整套服務 |

整合一律在 repo 內被忽略的 lab/data 目錄或明確設定的資料根，鎖 version/commit、license、hash、resource budget。核心 venv 不原地降級；subprocess/file contract 優先，不先新增通用 plugin framework。

## 執行順序與每包完成條件

| 工作包 | 內容 | 驗收／下一步 |
|---|---|---|
| A（本次） | 已確認錯誤修復、旧证据阻擋、計畫與交接 | focused/full offline、封存 hash 不變、提交推送與 PR |
| B（下次唯一主包） | 時間／目標契約 + 一個 factor 的最小 PIT 特徵切片 | 查重既有 asof/FeatureStore；公布資料盤點；future/revision/stale/holiday/roll 負測試；無資料用 synthetic 驗工程並標 DATA_NOT_READY |
| C | 一 baseline + 一個既有 ML challenger；只加最少 cross-market 特徵 | 新 protocol 先 commit/push；固定 splits；ablation／paired uncertainty／時間資源；不重用旧 final 調參 |
| D | 复用 V2 結構特徵 HH/HL、breakout acceptance、retrace | pivot 以確認時間可得，不用未來 pivot；證明比 C 有增益才保留 |
| E | bootstrap/EWMA path、quantile、尾部／regime 小實驗 | first-passage events 一致、ambiguous不灌成負樣本、calibration evidence 足夠才发布 |
| F | 成交量／微結構 | tick+volume 足夠才真 volume-at-price；OHLCV approximation 明示；缺資料不擋 B–E |
| G | Qlib 或 FinGPT adapter，擇有量測收益者 | dependency/license/resource 隔離；與 native baseline ablation 比較 |
| H | 含成本策略診斷 + 一個獨立引擎 parity | 同資料／session／tick／fees／slippage／roll，比對 orders/fills/PnL；不靠相似曲線過關 |
| I | FinRL-X 規則對照 sandbox（可完全跳過） | 必須在 H 之後；reward/cost/position 約束正確且優於規則；無增益刪除此方向 |
| J | paper/shadow + 可搬移安裝驗收 | 長期 shadow、reconciliation、stale gate、crash recovery；實盤是另外明確授權的專案，不在這份自動施工授權中 |

每包：確認實際起點 → 最小修改 → 相關測試 → 交接更新 → commit/push → PR/CI → 記錄 blocker/下一包。已授權的包內遇小問題持續處理，不因一個供應商沒資料就把整個專案停住；不要自動一口氣安裝 B–J 所有工具。

## 效能、風控與搬移

效能先量測 cold/warm p50/p95 latency、RSS/VRAM、資料新鮮度、CPU/GPU 佔用與 fallback。模型常駐/快取要有 source/feature/model/protocol hash；資料修訂要失效。禁止為省時間引用舊證據。GPU 重訓與 live recorder 分離排程，不平行跑多個重型驗證。

研究風控現在需要的是事件失效、staleness、缺資料、研究曝險情境與 abstain；不先建八個空風控檔。未來 paper 才做具體 OMS/reconciliation。JNU 一點每口 JPY10、tick5點即JPY50；notional、保證金、匯率、整數口數各自計算，不能把股票權重直接換成期貨口數。拒絕權限用顯式檢查，不以可被 Python -O 移除的 assert 作安全閘門。

搬移承諾是「可重建安裝」，不是複製 venv 就永久可用。project_root 與 MARKET_AI_DATA_ROOT 已有統一解析；使用相對路徑。新磁碟含空白／中文路徑做 clean clone + rebuild venv + dependency lock + offline core tests + stdio smoke；資料可配置別盤，credential 另在目標機建立，Windows SDK 位元／COM註冊／排程/launcher 另做 doctor。不要改動其他 D 槽專案，備份要排除密鑰與未授權行情。
