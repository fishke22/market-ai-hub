# 金融模型選擇、可信度與後續施工計畫

日期：2026-09-25。這是對程式的檢查與建議，不是已證明的市場績效。
檢查基線：`b56723357e7538309aba096013804781eb0a520c`，分支 `codex/quote-hub-correctness`。
本次修正 runtime build：`eca898aa6fc222c2`。Git commit、測試與上傳結果另見同目錄 `MODEL_CREDIBILITY_VALIDATION_2026-09-25.md`。

## 一、結論與現況

目前不應再大量加入預訓練模型。先讓既有模型在相同、可信的資料與同一組預測時間點比較，再補「風險分布」能力。模型多、彼此同意、程式測試通過，都不等於預測可信。

實際檢查範圍：model registry、既有基準與分類模型 adapter、tournament 評估、V2-H outcome 綁定、2I.1 評估、W3.1 governance、W3.2 forward cycle、W3.3 source contract、regime 與 public output 邊界。這不是對所有外部 SDK／所有模型權重的完整認證。

已有 Chronos-2、TimesFM、XGBoost、LightGBM 介面；FinCast 部分支援；Kronos-TW、Sundial、TTM、NHITS、NBEATSx、Moirai 為登錄或 challenger。亦有 naive、drift、moving average、seasonal naive、Ridge、VAR、dynamic factor、Kalman。Logistic regression 已在 BaselineClassifier 選項中，先重用，不重造。
registry 的 AVAILABLE 是工程狀態，不能直接當成目前權重已載入、已校準或勝過基準；本次未逐一載入大模型。

現在 W3.1/W3.2 工程已完成，W3.3 程式與離線合約已存在；不可再用舊 prompt 從 W2 開始重做。
W3.3 的 OSE tick-detail 時區仍未實測，tick 不等於 daily terminal close。實際 forward evidence 尚無、calibration fitting 尚未開始；常駐 recorder 載入新程式仍須另外驗證。
主交接文件仍停在 W3.2，W3.3 有獨立報告：每次以 bootstrap、HEAD、實際檔案校對，不把任何一份文件當永久真相。

## 二、要不要加模型

| 優先 | 補充能力 | 最小方案 | 啟動條件與拒絕條件 |
|---|---|---|---|
| 0 | 公平基準 | 保留 last-price、季節基準與既有 LR/Ridge；重跑受修正影響的排名 | 完全相同 target、horizon、cutoff、資料版本與預測 origins；缺資料不得縮小考卷偷偷獲利 |
| 1 | 波動與厚尾 | 先做 EWMA 波動基準，再以 Student-t GARCH(1,1) 為單一 challenger；非對稱殘差證據足夠才試 GJR/EGARCH | 有逐合約、無跨 roll 假報酬的序列；比較波動損失、區間寬度與覆蓋；估計不收斂則 abstain |
| 2 | 條件價格分位數 | 擴充既有 LightGBM 的 quantile objective，先 q10/q50/q90；沿用現有 adapter 與 audit | train-only 特徵處理、逐 horizon 訓練、交叉分位數檢查；不能由三個分位數推稱完整尾部／觸及機率 |
| 3 | 事件機率 | 已有 LR／XGBoost／LightGBM 對明確的 terminal/touch/first-passage 事件各自訓練，再獨立校準 | 必须有對應標籤與事件定義；日 OHLC 同日兩側都觸及時，先後順序標 UNKNOWN，不能猜 |
| 後續 | 狀態變化 | 重用既有 regime；在具體漂移問題出現後，才增加一種 change-point challenger | 必須降低樣本外失效／改善拒答，不能只增加漂亮狀態標籤 |
| 暫緩 | 更多大型基礎模型、深度強化學習、全模型 ensemble | 暫不新增 | 先證明不同模型錯誤具有互補性，且加入後在未參與選擇的資料上改善；GPU、授權、推理成本均需通過 |

以上是建議優先序，尚未新增模型、依賴或下載權重。GARCH 是風險／條件變異模型，不保證價格方向更準。Monte Carlo 是在假設下抽樣，不會自行產生已驗證的機率。免費下載權重也不等於允許商業使用。

## 三、提高可信度：必須留下哪些證據

1. **資料可追溯**：逐合約／月份、venue、session、event time、received time、available_at、source snapshot、缺漏與重複、價格單位、volume 語義、roll 與修訂版本。股票要處理公司行動及存活偏差。宏觀變數用當時可見版本。現貨代理不能冒充期貨。
2. **真正事前預測**：重用 W3.2，先在 target window 開始前封存 prediction/artifact/model revision/資料摘要，再等待成熟並結算。歷史 replay 和 FORWARD 分開。未知預訓練截止日的模型，不得把歷史回測稱成已排除預訓練污染的 clean OOS。
3. **依時間分層**：訓練 → 選型 → calibration → 最終測試 → forward。標準化、補值、特徵選擇全部只 fit 訓練集。TimeSeriesSplit 的 gap 只是工具，仍須依標籤實際起訖剔除跨分割重疊；不以隨機 K-fold 取代金融時間序列檢查。
4. **公平比較及缺失公開**：每個模型記錄 attempted／成功／拒答／失敗，以及 point、interval、event 各自有效樣本數。成對模型比較用共同 origins，同時呈現各自完整覆蓋率；不能只拿成功子集宣稱全面勝出。樣本數不等於獨立樣本數。
5. **多維指標**：POINT 用 MAE/RMSE 與同 horizon naive 相對損失；QUANTILE 用逐 q pinball；INTERVAL 同時看 coverage、width 及有效 n；EVENT 用 Brier/log loss、reliability bins、base rate、各 bin 樣本數。低 Brier 並不能单獨證明校準良好。
6. **估計不確定性**：按時間／交易日的成對 block bootstrap，保存種子、區塊長度與損失差區間；重疊 horizons 不用 iid bootstrap 假裝獨立。記錄所有嘗試過的模型／參數，控制多重比較；最終測試被拿來調參後就不再是 final test。
7. **樣本門檻要事前登錄**：依機率誤差容忍、事件基率、正負樣本、有效樣本量與各 regime 覆蓋決定；不能把 2I.1 的 MIN_PROBABILITY_SAMPLES=2 當可信門檻，也不能宣稱任意 100／500 筆必然足夠。先定驗收規則，再看結果。
8. **校準是獨立工序**：先保存 out-of-sample 原始分數，再用獨立 calibration window fit sigmoid；資料量足夠才比較 isotonic。另用 untouched evaluation window 驗證，按商品／期限／事件族分開。校準證据綁 dataset、模型版本、事件定義、日期與失效條件；漂移後降級而非永久 CALIBRATED。
9. **分析價值與交易價值分開**：先證明預測優於基準；之後才以費用、spread、滑價、延遲、成交機率、流動性與尾部虧損研究 reward/risk。Buy/Profit 等區域先當研究情境，不直接成為下單指令。下單功能不在本工作範圍。
10. **主腦只能解讀可追溯結果**：資料時間、商品、期限、當前位置、可用區域、機率證據、失效條件與缺漏必須一致；無機率時說「尚無校準機率」。不要把信賴區間、模型分歧、分類分數、模型原生分位數混叫勝率。每個數字能回到 artifact；檢查白話回答是否捏造數字或改變條件。

## 四、本次已修正

| 問題 | 原行為 | 修正及影響 |
|---|---|---|
| 事件答案混用 | 同屬 TOUCH 的 UP/DOWN 標籤可互綁 | append_outcome 要求精確 label_type；2I.1 同時拒絕歷史錯配資料，回 WRONG_EVENT_DEFINITION，不改寫舊 DB |
| 季節性基準期限錯位 | 1、2、5、10 步都取同一個 lag；剛好五筆還退回 last-price | 按 horizon 在最後五筆周期取正確終點；仍是五個觀測值的簡化周期，不代表每個市場真有週季節性 |
| 區間評估錯配／無效區間 | 上下界分別去空值，可能混合不同 origins；忽略 quantile_valid | 依 point 的 origin 對齊，僅使用成對有限且 lower<=upper 的界線；無效 flag 不進評估；輸出 interval_sample_size；零價格不算無限相對寬度 |
| 虛構信賴區間 | 每個趨勢固定套用 Wilson(0.5,200) | 移除假估計，confidence_interval=None、confidence_status=NOT_ESTIMATED；未憑空設計新信心水準 |
| 分類預測列錯位 | valid labels 後又刪 horizon 筆，並預測舊訓練最後列 | XGBoost/LightGBM 共用 adapter 改預測 cutoff 最新特徵；只以成熟標籤訓練；最新特徵缺失則拒答 |

五類修正均有先失敗後通過的回歸案例（區間問題有兩種測試，分類測試涵蓋兩種 adapter）。同步刷新既有 build snapshot 測試，不把新 runtime hash 當成舊 recorder 已升級的證據。
受影響的舊 tournament 分數／排名與趨勢信賴欄位不得沿用為新版本的有效性證據；保留歷史檔案及其版本，另產生新版本結果。

## 五、下一階段分包，不一次重造系統

**C1 評估比較補強（現在可做）**：驗證本次修正已在當前 HEAD；審查並修正失敗／拒答統計、共同 origins 比較、資料／模型版本指紋。檢查 random_walk 抽單一歷史報酬且忽略 steps、classification_baselines 缺 train_labels 時引用測試答案、rates regime 回看索引等既有路徑。逐一追所有 callers，補重現再最小修正；不可把未重跑的舊結果當最新。補充本文測試未涵蓋的非有限數值與歷史 manifest 邊界。

**C2 真實資料與 forward（須來源條件）**：W3.3 單一 owner 的受控時段實測、日期時區與交易明細涵蓋驗證；最後成交不自動等於 terminal close。先證明完整收盤語義再寫專用 DAILY feature，接既有 W3.2。未有維護窗口授權不可擅自 restart/login；可繼續其他離線工序。遇休市、roll、缺漏應拒絕樣本，不回填成事前預測。

**C3 最小分布 challenger（C1/C2 輸入成立後）**：只做 EWMA + 一種 GARCH challenger，或先重用 LightGBM quantile；一次一種，保持 naive 對照。先 retrospective engineering evaluation，再封存 protocol 做 forward。無資料時完成離線 contract 並標示等待證據。

**C4 校準及發佈門檻**：重用 W3.1 與 2I.1，加入獨立 calibrator artifact／validation gate，而非把 EVALUATED 改名 CALIBRATED。先以真實成熟、同質、獨立窗口樣本證明；fitting 完成也不自動開放所有事件機率。

**C5 Price/Probability Map 與白話驗收**：terminal 區間落點、期間 touch、first passage 分別定義與驗證。互斥完備 terminal bins 才要求總和一；touch 是非互斥事件，不能強迫總和一。共同路徑／joint dependence 未知時，不得由 marginal probabilities 編造先後／策略 EV。沒有路徑資料，保留 terminal map，first passage=NOT_AVAILABLE。所有白話描述附失效條件，資料過期／模型漂移立即降級。

每包成功後：相關測試、offline profile、diff/秘密檢查、更新交接、專屬 commit、push、記錄 PR 與 CI。不得順手提交他人 staged files。不要因一包資料等待而停止所有可做的離線工作。

## 六、免費第一方／作者資源

下列頁面可免費閱讀；套件／權重採用前仍須核對特定版本授權、硬體和依賴。不以「免費」推論無使用限制。

- 基準定義（作者教材）：https://otexts.com/fpp3/simple-methods.html
- GARCH、模擬與殘差假設：https://arch.readthedocs.io/en/latest/univariate/forecasting.html
- Student-t／非對稱波動模型：https://arch.readthedocs.io/en/stable/univariate/univariate_volatility_modeling.html
- LightGBM quantile objective／alpha：https://lightgbm.readthedocs.io/en/latest/Parameters.html
- Calibration、資料分離、可靠度圖：https://scikit-learn.org/stable/modules/calibration.html
- 時間順序與 gap：https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- 時間序列 block bootstrap：https://arch.readthedocs.io/en/latest/bootstrap/timeseries-bootstraps.html
- OpenCode 模型／provider 與 variant 文件：https://opencode.ai/docs/models/

本次未修改 OpenCode 設定、未核定本機 DeepSeek 實際 provider/model ID；不要從使用者俗稱猜版本或推理欄位。ChatGPT 新對話應優先讀本文件及最新 repo 交接，再選一個可驗收的包。
