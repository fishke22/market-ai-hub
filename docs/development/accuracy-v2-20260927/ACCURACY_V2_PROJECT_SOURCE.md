# MARKET_AI_HUB Accuracy v2：預測能力提升與施工契約

版本：2026-09-27 Accuracy v2。文件性質：研究與施工規劃＋可替換實作快照。**P0/P1/P2 已完成工程落地；P2 development 的實際結果是 NO_IMPROVEMENT、保留 baseline，P2 新 final 尚未開啟；其餘方法仍是候選。** 本文件取代同日 vNext 的模型優先序與下一包設計；保留既有修復、資料治理、quote-only、安全與搬移規範。不要並列兩份互相矛盾的「最新版」指示。

## 0. P0/P1 實作快照（2026-09-27）

- 實際施工分支 `codex/vnext-audit-handoff`，本包進場 base HEAD=`fc6bd6830ecfed642c3c268e953ec3385eac08b8`；source/config worktree build=`a11cbb922621e730`。既有 `scripts/register_jpx_micro_sync_task.ps1`、`scripts/run-hidden.vbs` 保持未追蹤且未提交。
- P0：本機 x64 venv 是 Python 3.12.13、`chronos-forecasting==2.3.2`、`timesfm==3.0.2`。Chronos-2 registry revision=`29ec3766d36d6f73f0696f85560a422f50e8498c`，TimesFM-3.0=`43046b85ec22d584a13f8098c2ed39c889e129c2`；兩個 exact snapshot 都存在本機 cache。loader 現在都明確傳 registry revision，不再以「cache 第一個 snapshot」當 loaded revision。
- Chronos-2：官方/目前安裝 API 的 `Chronos2Pipeline.predict`/`predict_df` 支援 multivariate、past covariates 與 future covariates；本地 `ChronosAdapter.predict` 仍只餵單一序列，因此 `upstream_support=true`、`adapter_implemented(covariates)=false`、`local_verified(covariates)=false` 分開記。一次 `HF_HUB_OFFLINE=1` 的 pinned CPU actual load 在 120 秒逾時，沒有取得 runtime commit attribute，因此 loaded-revision `local_verified` **維持 false**，不拿 cache presence 代替實載證據。[R2]
- TimesFM-3.0：官方權重條款明確是 non-commercial / non-production。adapter 預設 purpose=`UNKNOWN` 並 fail-closed；研究 tournament/smoke 必須明示 `RESEARCH`；serving singleton 與 deep health 明示 `SERVING` 而被 gate 阻擋。shallow status 顯示 `RESEARCH_ONLY_AVAILABLE_NOT_LOADED`；權重未刪除，沒有啟動/切換 live service。[R3]
- P1 target contract 已落地：`decision_time`、`reference_price`/`reference_price_available_at`、`target_start`/`target_end`、`target_measure`、`exact_contract`、`forecast_horizon`、`label_available_at`。full-interval forecast 強制 `decision_time <= target_start < target_end`；reference 必須已可得；label 不得早於 target end。
- JNU 語義分離：`NEXT_OSE_SESSION_SETTLEMENT` 與 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION` 是不同 target。JPX Daily Report 官方說明約於**次營業日 09:00 JST**更新；假日交易統計會與假日前夜盤/後續營業日資料合併，不單獨發布，因此不得把 holiday-session outcome 假裝在前一日 15:45 已知。[R8]
- 一個跨市場切片已完成：沿用既有 FeatureStore/as-of provenance，固定 exact factor contract，產生 `factor_lagged_return = latest/prior - 1`。packet 保存 event/available/received/provider time、provider/source/frequency、venue/session、relation、contract、snapshot/lineage、age 與 source/value content hash。拒絕 future/late、非 PIT、安全狀態錯誤、stale、proxy relation mismatch、roll、series semantics/contract mismatch、duplicate time、non-finite、缺 bar gap、snapshot 缺失；future revision 不改過去 packet；labels 不進 features。
- 實際資料只讀盤點：目前 FeatureStore 存在，但 NQ/ES/JY/TMF 候選 representation 沒有合格歷史列可形成本包 packet。因此本包只用 synthetic temporary data root 驗工程，明確輸出 **ENGINEERING PASS / DATA_NOT_READY**；沒有造行情、沒有新增付費來源、沒有 market validation。
- Cache identity 現在包含 target contract、source lineage/snapshot/timestamps/value-content hash、feature version/formula、model revision 與 protocol version；相同日期但內容/revision不同會失效。
- 驗收：focused package/regression=`66 passed, 44 warnings`；針對首輪 full offline 的 4 個預期整合修正後 fixcheck=`4 passed`；final offline（只排除既有 live recorder owner mutex 測試）=`2024 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。mock/synthetic 僅證明工程。HPQ1 131/48 封存沒有重跑/覆寫/解封；W4 門檻未下降。
- P2 入口固定為：**先 commit/push 新 protocol**（primary loss、naive delta、chronological splits、trial cap、label-overlap purge/availability、seed、新未曝光 holdout），再做同 origin 的 last-value naive＋既有 linear/classifier 基準＋一個 LightGBM 任務，產生 walk-forward OOF ledger 並只做有限搜尋。沒有新證據則保留 baseline；Chronos-2 past-only covariate ablation 延到 P3。

## 0.1 P2 實作與第一個 development 結果（2026-09-27）

- P2 protocol 在任何 Ridge／Logistic／LightGBM outcome 前先提交並 push：`f2edd7c`；內層 tie/coverage 與 final static-training/inference-context 規則再於**仍未跑 candidate 前**凍結為 `53386f54740e2bcd0706140f6c4df5aeb80facab`，且當時 HEAD=origin branch。這兩個 prereg commit 是後續 engine 的前置證據。
- 任務改用 publication-causal `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION` return regression，避免重用 HPQ1 已阻擋的 next-session horizon。主要 loss=`MAE_RETURN`、baseline=`ZERO_RETURN`、`d=loss(candidate)-loss(naive)`，負值才代表 candidate 較佳；最小實質改善固定為 0.0005（5 bps）。這個 delta 在 candidate 前由 43-origin pilot 的 naive MAE=`0.01554320` 尺度設定，約 3.2%，不是看完 challenger 再調。
- Development 只到 2026-07-10；2026-07-11..2026-09-27 明列 `EXPOSED_QUARANTINE`，禁止 fit/selection/claim。新的 final 僅接受 2026-09-28 起 publication-origin，最少20個，且一用；開發 outer folds 看過後都視為 development information。
- P2 features 固定10個自有歷史因果量：1..5期lag return、5期平均return、5/20期vol、publication weekday、到期日天數。P1 跨市場 factor 因真實資料仍 DATA_NOT_READY，P2 明令禁用；label/future-fill/full-sample scaler/winsor 也禁用。
- Nested walk-forward 固定為 expanding outer min-train32/test10/max5；inner min-train20/validation6/max3；每折一個 origin embargo，且只允許 `train.label_available_at <= evaluation.decision_time`。Ridge 僅3個 alpha；LightGBM 僅4個小型 `regression_l1` 設定；seed=42；失敗trial也算cap；inner/outer同-origin coverage均須100%。LogisticRegression沿用既有 `BaselineClassifier("lr")`，只評方向、不能選 return champion。
- 第一個且已凍結的真實 JPX development artifact 位於 gitignored data root，ID=`40ecb8c9bd585f882f76e9bc`，protocol hash=`6f5b98cd29e6cb9a75b6db69bd0a3e688a802735b57f406665b0f7a5bb37cb82`，development source fingerprint=`72f9e633f157069479d0982c4ea7e48677d3db9b9ed5cd58824607037d11f0cb`。83 development origins／48 quarantine／0 final-forward；5 outer folds產生50個同-origin OOF；35 inner trials全部 eligible，無 model error，故不是因模型missing才回退。
- OOF：zero-return naive MAE=`0.0171708858`；LightGBM MAE=`0.0176094085`、delta=`+0.0004385227`、paired 95% CI=`[-0.0010278175,0.0017445661]`；Ridge MAE=`0.0189684494`、delta=`+0.0017975636`、CI=`[-0.0002190782,0.0039799257]`。兩個 challenger 的平均 loss 都比 naive 高；CI也沒有達到 prereg `upper < -0.0005`。因此 selection=`zero_return_naive`，明確 `NO_IMPROVEMENT`，不硬選複雜模型。
- Logistic獨立方向診斷：n=50、coverage=1.0、balanced accuracy=`0.278431`、majority accuracy=`0.40`、log loss=`1.152191`；沒有支持另行升級方向模型。
- P2 final **沒有開啟**：新 final origins=0，且 development 已保留 baseline。結果仍是 `DEVELOPMENT_INFORMATION_ONLY`／`not_final_holdout_evidence=true`／`not_calibration_evidence=true`／`not_trading_edge=true`；不得改寫成模型已被 final 證明失敗或成功。
- P2 驗收：engine/protocol=`10 passed`；focused P2/P1/HPQ1/build=`36 passed`；full offline（只排除既有 recorder owner-mutex 測試）=`2034 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。舊 HPQ1 131/48 沒有重跑、覆寫或當新 final 使用。
- 下一包 P3-A 只先施工 Chronos-2 past-only covariate adapter＋future-covariate fail-closed＋synthetic/PIT負測試。因 real cross-market factor 尚 DATA_NOT_READY，不能先跑真實 covariate 增益；residual shrinkage／組合等到單一 covariate path 可因果驗證後再做。

## 1. 結論：保留底座，修改模型策略，不整套推倒

沒有在所有金融商品、時段與市場狀態都最高準確率的固定模型。此專案應建成「持續找到並保留當前有證據的最佳模型」的系統，而不是宣稱某個模型名就是最強。我的選擇是：**高品質可得時間資料＋分任務的小型專家模型＋既有 Chronos-2 外生變數實驗＋受限制的組合＋獨立前向驗證＋能拒絕過度判斷的發布層**。

改善分三類，不可混為一談：

- 可能增加可預測資訊：更可靠的目標資料、跨市場因子、合格的微結構／事件資料。
- 可能改善預測估計：報酬／殘差模型、適量共享訓練、受約束組合、適應不同波動狀態。
- 改善可信度與區間：防洩漏、獨立比較、校準／conformal、拒答與漂移監測。這些不自動提高方向命中率；驗證變嚴格可能使表面準確率降低，卻更接近真實。

近期金融 TSFM 比較研究在五檔美股發現相對 random walk 的顯著改善有限；它不是 JNU 或 TimesFM-3.0 的排名證據。故不直接採用排行榜冠軍，也不承諾固定 80%／90% 勝率。[R1]

## 2. 本次重新核對的實況

- 實際 repo：`D:\MARKET_AI_HUB`；遠端 https://github.com/fishke22/market-ai-hub 。路徑只用於定位，不是新的硬編碼要求。
- 起點 HEAD：`3033efd4aef7ae32055c7865ce94930daf3a8a36`，分支 `codex/vnext-audit-handoff`，build `dff534ae24a053c7`。PR #74 重新查詢為 OPEN、CI SUCCESS，未合併。後續文件提交不改 runtime build；進場仍重新查實際HEAD。
- 上一包修復驗收：1995 passed、1 skipped、35 deselected；這是上一包程式驗證，不是本次新模型測試。本次未重新訓練、未開新市場評估、未更換運行模型。
- HPQ1 131-origin封存有9/18→9/24跳過OSE假日交易的horizon錯配，已BLOCKED；原48筆final已曝光，不可重用。封存ID `3f28cec82268445d7d377356` 保留不變。
- 既有 V2、2H.4 audit、W3.1、W3.2、W3.2-EP1、W4.1 calibration fitting、W5.1 first-passage 不重建。
- 本機套件：chronos-forecasting 2.3.2、scikit-learn 1.9.1、LightGBM 4.7.0、XGBoost 3.4.1。
- `ChronosAdapter.predict` 目前只把單一序列轉成 `[1,1,time]`，未餵跨市場協變數；registry 的 supports_covariates=false 描述本地能力缺口，不能誤讀成上游模型不支援。官方 Chronos-2 支援 multivariate/covariates，但尚待本地 adapter 與 PIT 檢查驗證。[R2]
- 已有 logistic regression／random forest／LightGBM／XGBoost **方向分類器**。規劃的 return regression／quantile regression 是新任務，不等於現有分類器已能輸出可靠價格分布。
- P0 前的缺口是 Chronos loader 未明確傳 registry revision；P0 已改為明示 pinned revision。實際 pinned offline load 曾在120秒逾時、未取得 runtime commit attribute，因此 `local_verified` 仍維持 false，不能拿 cache snapshot presence 當成實載版本證據。
- bootstrap 中 callback 狀態是歷史 capability 記錄，不是本次登入測試，也不能推出連續多年行情。硬體以目前設定 RTX4060Ti 16GB 為研究預算，實際可用VRAM仍要量測。

## 3. 舊設計如何處理

| 原設計 | 決策 | 修訂 |
|---|---|---|
| Hub治理／audit／W4／W5／MCP白話輸出 | 保留 | 新功能走原契約，不另建第二套評估或資料庫 |
| Price Map / Probability Map | 保留並嚴格分流 | 終點、touch、先後、尾部各有labels／模型／評分；缺一就NOT_AVAILABLE |
| Chronos與TimesFM固定等權 | 降為研究對照 | 不作預設最強答案；與naive、直接ML、受約束組合在同origin比較 |
| 所有模型都給一個confidence | 排除 | 區分raw score、機率、已校準機率、樣本不確定性、資料品質 |
| 先把Qlib/FinRL-X等全接上 | 延後 | 先用現有依賴完成可量測增益；框架不直接等於精度 |
| 大模型／多agent彼此投票 | 排除為統計證據 | 主腦負責可追溯解釋，不能投票產生行情勝率 |
| 以OOS小幅勝出就稱有效 | 取代 | 固定協議、搜尋帳本、配對不確定性、獨立forward與實質效果門檻 |
| 每次必給明確漲跌／交易建議 | 修改 | 數值研究預測可保留；發布方向判斷可abstain，並同時公布覆蓋率 |
| RL／OMS／自動交易 | 不進精度主線 | 僅在預測、成本與獨立回放完成後另評估，實盤仍需另外授權 |

**TimesFM-3.0另有實際選型限制**：官方權重授權明列非商業、非生產用途，不能只看程式repo的Apache標示就當可自由部署。新版把它放在授權允許的隔離研究比較中，排除為預設生產／對使用者服務的必需模型。實作時核對實際取得revision的條款並建立執行用途gate；本次沒有擅自刪除權重或改運行服務。可商用開源路徑優先既有傳統ML與授權核實的Chronos-2，不另購商業授權。[R3]

## 4. 先定義「準確」與預測時點

第一條研究線沿用 JNU exact-contract 日級任務；其他商品可套契約，不能直接沿用其勝率。先完成單一horizon，再獨立擴充2／5交易日；盤中5m／15m／60m是不同研究線，必須等真實盤中資料足夠。

| 任務 | 主要評分 | 必須同步報告 |
|---|---|---|
| 終點價格／報酬 | 預登記的MAE或MASE相對naive | RMSE、尾部誤差、同origin覆蓋、方向、各regime；MASE分母僅由訓練段定義 |
| 漲／平／跌 | multiclass log loss 或預定proper score | balanced accuracy、各類precision/recall、base rate；flat band在train固定 |
| 分位／區間 | pinball或weighted interval score | 名義／實際coverage、width、分組coverage、crossing |
| touch／first-passage | 事件Brier或log loss | 明確事件族、觀察窗、ambiguous／censored比例、sample n |
| 發布的方向訊號 | 固定覆蓋率下的錯誤／risk-coverage | 全部合格origin的表現、每類樣本量、拒答原因；不可只秀少數命中案例 |

不靠高價商品的price R²、MAPE很小、平盤類佔多數的accuracy，或極寬區間的高coverage當主要成功指標。價格誤差降低、方向判斷較佳與含成本獲利是三個不同目標。

機率評分只接受定義清楚、有限且位於[0,1]的event probability；多類機率須和為1。CLASS_SCORE不得直接送入Brier/log loss；未校準predict_proba可用於研究評分，但不因此升級為可公開的已校準勝率。

預測契約至少包含 decision_time、reference_price及其available_at、target_start/end、target_measure、exact_contract、forecast_horizon、label_available_at。`available_at <= decision_time < target_end`；若聲稱預測完整區間報酬，decision_time還須不晚於該區間起點；中途開始只能另定義剩餘期間／nowcast任務。

JPX Daily Report 通常次營業日約09:00 JST發布，假日可能合併。**next OSE session settlement** 與 **next published settlement observation** 必須分成不同target，不能把後者標1d。上一日結算價若只在次日已開盤後才知道，就不能假裝在上一日收盤已出預測。若用即時last trade/midprice作新基準，資料語義也要另立契約；不默默把last trade當settlement。[R8]

## 5. 精度主線：分層專家，不建立大而全的新平台

### 5.1 資料優先與合理擴充

先選一個有可驗證歷史的外部factor，做availability-aware backward as-of join。保留event_time、received_at、known/revision時間、source_hash、venue/session、representation、exact contract、age與缺值原因。只使用當时已知修訂；feature_available_at為所有輸入最晚可得時間加合理計算延遲。歷史假設與實際接收紀錄分欄，不捏造歷史received_at。

JNU／日經mini／大型期貨有共通資訊，但微型目標有自己的成交、價差與換月。可把同期同到期月mini／large作特徵或共享訓練候選，**不能替代JNU outcome**。同日多限月不是獨立樣本；所有商品／限月用相同時間切分並按origin/session分群估計不確定性。跨商品預訓練還需leave-instrument-out診斷與最終JNU留出；禁止把JNU未來透過其他商品同日資料洩漏回來。

日级候選順序：自身lagged return／EWMA volatility／期限與session → 同步合約basis（有資料才做）→ NQ/ES、JPY相關價格、VX、台指等少量落後特徵 → 事件。NQ不等於SOX；JY futures不等於USDJPY spot；VX不等於VIX；ZN不等於殖利率。lead-lag是待驗假設，不是已知因果。

盤中只在有timestamp可靠的quote/trade/depth後增加spread、book imbalance、microprice、OFI與成交特徵。quote snapshot足以算某些depth imbalance，但不能假裝有完整order-flow事件。OFI研究支持它作候選資訊，主要是其他市場的價格形成關係；不能從同期相關直接推論JNU未來可交易alpha。[R7]

### 5.2 候選模型的最小集合

1. **Baseline family**：last available price、zero return、causal drift/rolling mean，以及方向的majority/base-rate。每個候選與基準同origin/target/資訊集評分。
2. **可解釋ML**：既有logistic用於方向；小型Ridge/ElasticNet回歸作return baseline。新增return regression須和現有classification分開model_task，不拿class score當價格分位。
3. **LightGBM主challenger**：小深度、受限葉數的return regression與quantile regression；XGBoost作第二候選，而非同時大量搜尋。先20個以內、可解釋的特徵；這是初期工程預算，非最佳維度定律。[R9]
4. **Chronos-2改造候選**：先univariate和past-only covariates對照，再評估multivariate。future covariates只容許origin已知的日曆等；不得輸入未來NQ價格、事後新聞或未來波動。先核對安裝版API和實際權重revision，不盲目改registry flag。[R2]
5. **小型波動專家**：EWMA＋經驗殘差bootstrap先做；realized intraday variance可用時才試HAR-RV；GARCH-t只在額外實測勝出才加套件。波動更準不自動代表方向更準。

不先加入Moirai、PatchTST、TFT、LSTM、KAN或再添數個foundation模型。若上述候選的具體失敗分析顯示其不可替代功能、且資料／硬體可負擔，再只加一個有清楚假設的challenger。FinCast、Kronos等既有可選模型保留原研究狀態，不因本次規劃自動升級。

### 5.3 報酬、殘差修正與保守組合

直接price-level模型保留作對照；嘗試log return／以origin波動尺度標準化的return，還原價格時維持同target與unit。scaler、clip、winsorize均只能fit於train；不能整段去極值後再切分。單調exp轉換保留對應分位，但平均價格不能隨便用exp平均log return替代。

第二階段可用 `forecast = baseline + lambda × predicted_residual`；lambda包含0並僅從inner chronological validation選擇。這是待驗的shrinkage設計，不是數學保證。residual training只用out-of-fold的base predictions，不能用同一段fit後的in-sample誤差。

組合先等權baseline，再非負／和為1、低自由度的權重；只用時間因果OOF資料學習權重。樣本不足時回退naive或單一勝出模型。不同模型錯誤高度相關時，不把數量當分散效果。

不能直接使用StackingRegressor預設KFold，也不能只指定shuffle=False就聲稱沒有未來資訊：某些fold仍用測試區段之後的樣本訓練。需要明確walk-forward OOF生成器，只在有歷史OOF預測的列fit二層；不以in-sample預測補早期缺列。[R5]

均值、分位與機率組合各有契約。平均p10/p90只是quantile aggregation，不是一般mixture distribution的分位。若混合完整分布，需用其CDF／samples重新求分位並重新驗證；不從兩條端點分位拼出first-passage機率。

### 5.4 Regime、校準、conformal與拒答

先用train限定的低／高波動、趨勢／盤整、開收盤session等少量狀態。每state樣本不足則縮回global模型，不能用HMM切成許多小段挑勝者。滾動／expanding window、recency weight與retrain cadence都是有限預登記候選；不因剛輸一天就即時換權重。

W4事件機率校準繼續沿用，不降低既有門檻。模型版本、事件族、horizon與校準資料綁定；改base model可能使舊calibrator失效。小樣本不優先高自由度isotonic，也不把較低Brier單獨當充分校準證據。[R6]

新增 **adaptive conformal interval** 只作「區間覆蓋與寬度」challenger，和W4事件機率不是同一功能。只能在outcome到達後更新residual buffer；多步label延遲也要等待。時間相依／漂移下不能套用IID split-conformal的條件而宣稱每次都90%保證；評估rolling coverage、width、interval score、各state及異常期間。此方法可以補可靠度，沒有保證提高point MAE或方向命中率。[R4]

弱訊號／資料過期／模型分歧時，可以不發布強方向建議；要同時保留全部origin預測與拒答記錄。固定coverage levels例如50/75/100%只作評估曲線，發布門檻與最低覆蓋率在validation選定並凍結，不事後改到最好看的命中率。interval width、model disagreement不是已校準勝率，品質分數也不能叫probability。

## 6. 能分辨真進步的驗證規格

### 6.1 時間與搜尋預算

先登記instrument、target、decision時點、資訊集、主要loss、最小有意義改善delta、split、purge規則、候選/特徵集、trial cap、seed、runtime budget、校準、停止條件與發布用途。delta由train/pilot噪音與產品用途設定數值，在test前固定；不看final再挑門檻。

初期每一target/horizon建議至多3個模型family、每family至多8組設定、每組至多3個固定seed；包含失敗/淘汰，不重新命名experiment以清空搜尋次數。這是可調的算力與過擬合控制預算，不是統計最優值。資料不足時縮小搜尋，不湊數。

使用nested chronological walk-forward：inner選特徵／hyperparameters；outer評估固定選擇流程；再保留一次final與新的真實forward。outer結果看過後若修改流程，需標為已用development information，不能繼續叫未碰過test。一般nested-CV文档的隨機Iris範例不能原封套金融時間序列。[R5][R10]

purge以真實label時間區間、label_available_at與feature availability處理；例如5天label相鄰origins高度重疊，不能只在資料列間gap=1。若使用blocked split，embargo長度依最大horizon與延遲預定。PBO/DSR可作大量策略搜尋的額外診斷，不替代因果walk-forward或預測loss比較。[R11]

### 6.2 成功與淘汰

- baseline與candidate在相同合格origins比較；模型missing/error仍列coverage，不能丟掉難日讓它勝出。
- `d = loss(candidate) - loss(baseline)`；固定的paired block/bootstrap CI，上界低於預登記的`-delta`才支持實質改善。block應涵蓋label overlap／合理序列依賴，cluster同日商品；不同block敏感度是診斷，不挑顯著版本。
- 多候選結果全記錄；validation挑一個final候選可避免把每個候選都拿final選。若仍多重正式檢驗，protocol事先定義校正方式。
- 主要loss通過且coverage、tail loss、regime穩定性、延遲／VRAM沒有超出預定退化上限，再允許shadow晉級。新forward同時跑baseline，使用固定觀察點或預定序列檢驗，避免每天偷看p-value決定何時宣布成功。
- n不足／CI太寬／沒有勝者＝INSUFFICIENT_EVIDENCE或NO_IMPROVEMENT，預設保持baseline。不把等待說成失敗，也不把勉強選第一名說成高精度。
- 先前W4的50/50/50與30日等門檻沿用但非萬用保證。新增任務要根據不確定性與有效樣本數規劃；日級幾百筆不因切成大量重疊window變成大量獨立實驗。
- 模型只在完整授權與用途相符時才能進發布集合；license_blocked與accuracy_failed分開。

### 6.3 可解釋呈現

研究頁每次顯示：target／decision/reference日期、資料age、point/interval、可用的event probabilities、baseline、當前champion與evidence grade、樣本數、固定區段結果、實際coverage、model disagreement、失效條件。feature importance或SHAP只作預測關聯解釋，不說成因果；不能解釋模型根本沒有吃到的NQ／新聞。

示例措辭：「這次模型區間比上一次寬，代表不確定性增加。跨市場資料支持偏多情境，但目前尚未證明它在新資料上穩定優於沿用最近價格，因此保持研究觀察，不發布可靠勝率。」數字全部從實際packet取得。

## 7. 開源工具與效能：只在用途清楚時加入

Qlib仍保留獨立research adapter候選；Hub研究extra MLflow3.16.1與先前核對的Qlib mlflow<3.13不能共裝。FinGPT只用於有timestamp/來源的事件抽取與ablation；FinRobot不另建第二個主腦；FinRL-X延後到可信成本與回放後；LEAN/Nautilus先擇一做離線parity，非精度主線。LEAN CLI付費限制、Nautilus v2 RC、生產用途授權仍依前包來源檢查。[R12]

模型載入與重訓不得搶占recorder；一次一個重型job。先量p50/p95 inference、cold load、RSS/VRAM、timeout/fallback；memoization key含input/feature/source/model revision/protocol hash。只在dirty source cache失效後更新，不引用舊指標。precision/quantization/CPU-GPU切換須數值回歸，不能為速度讓分位無效。16GB是設定上限而非實際保證可用容量；保留OS／其他程序餘裕。

增加歷史資料只走已授權broker累積或可合法免費公開資料，不宣稱免費取得完整多年期貨tick。禁止付費雲端、SageMaker部署、買行情作本計畫必要條件。dataset、code、weights、API與再散布條款各自核對。搬移用既有project_root/MARKET_AI_DATA_ROOT，重建venv、SDK/launcher/task與WinCred，不整個複製權重密鑰到Git。

## 8. 新施工順序（取代舊B–J的模型優先序）

| 包 | 交付 | 必須通過／不做什麼 |
|---|---|---|
| P0 | 核對PR74、版本／license／loaded revision與能力差異；選定research/serving用途 | metadata≠runtime；保留兩個原untracked檔，不merge、不重啟recorder |
| P1（本回合施工目標） | decision/target/publication契約＋一個PIT factor＋cache identity＋可重現packet | late/revision/future/holiday/roll/stale負測試；無真實資料以synthetic验工程，不升級精度 |
| P2 | 新protocol、naive/Ridge/既有logistic與一個LightGBM任務、chronological OOF ledger | 使用新未曝光test；先小搜尋，class score與return任務分離 |
| P3 | Chronos-2 past-only covariate對照＋residual shrinkage／簡單受限組合 | 每次只加一項，ablation证明增益；不先fine-tune |
| P4 | 波動／quantile＋必要的regime縮減與interval conformal | 延遲outcome正確、proper score與width；不取代W4事件校準 |
| P5 | 新forward累積、固定發布gate、abstain/coverage與drift降級 | no improvement回baseline；沒有資料不虛報CALIBRATED |
| P6（條件式） | 盤中OFI、共享訓練、新聞或fine-tune，每次擇一 | 先證明資料與runtime可行；需獨立增益才保留 |
| P7 | 一個獨立引擎、含成本診斷、paper与搬移驗收 | 執行／交易可靠性分開驗證，不擴充成實盤授權 |

每包先讀repo、找既有helper，再做最小差分、測試、交接、commit/push與PR/CI；成功的意思是工程／資料／效果各自有證據，不是勾完框架安裝清單。P0/P1本次新對話直接施工，其他包在其前提達成後接續，不一回合越級全部安裝。

## 9. 免費官方／原始研究來源

以下於2026-09-27查閱；方法論證據支持「值得測試」，不代表已證明對本系統有效。

- **R1** [Financial return TSFM benchmark, 2026 preprint](https://arxiv.org/html/2606.27100v1)：讀取方法與限制；五檔美股、既定模型版本，不能外推JNU或把forecast error當alpha。
- **R2** [Chronos官方](https://github.com/amazon-science/chronos-forecasting)、[Chronos-2模型卡](https://huggingface.co/amazon/chronos-2)：多變量／外生能力與權重；其benchmark宣稱不直接移植為本專案效果。
- **R3** [TimesFM-3.0權重授權原文](https://huggingface.co/google/timesfm-3.0-pytorch/raw/main/LICENSE)、[程式repo](https://github.com/google-research/timesfm)：免費研究不等於免費生產／商業用途；以實際revision條款為準。
- **R4** [Gibbs & Candès, JMLR 2024](https://jmlr.org/papers/v25/22-1218.html)：online adaptive conformal；用於區間適應，不當單次條件勝率保證。
- **R5** [StackingRegressor官方](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html)：OOF與預設CV需注意；本計畫的chronological OOF是為本系統另設的約束。
- **R6** [Probability calibration官方](https://scikit-learn.org/stable/modules/calibration.html)：可靠度曲線、校準方法與資料分離。
- **R7** [Cont/Kukanov/Stoikov, order book events](https://arxiv.org/abs/1011.6402)：價格形成與OFI；樣本為美股，不能當JNU未來方向已驗證結果。
- **R8** [JPX Daily Report](https://www.jpx.co.jp/english/markets/statistics-derivatives/daily/index.html)、[OSE假日交易](https://www.jpx.co.jp/english/derivatives/rules/holidaytrading/index.html)：publication與session不能混用。
- **R9** [LightGBM參數](https://lightgbm.readthedocs.io/en/stable/Parameters.html)：regression/quantile與正則化選項，對應安裝版4.7.0使用。
- **R10** [Nested CV官方說明](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html)、[TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)：選模偏差與時間切分；金融label overlap仍須額外治理。
- **R11** [Bailey等，Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)：保留搜尋次數與防止選最好回測；不能把PBO當前向通過證明。
- **R12** [Qlib dependencies](https://raw.githubusercontent.com/microsoft/qlib/main/pyproject.toml)、[LEAN CLI prerequisite](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started)、[Nautilus官方](https://github.com/nautechsystems/nautilus_trader)：前包已核對的隔離與免費界線，真正安裝前重查固定版本。

## 10. ChatGPT施工與跨對話規範

WebCodex主施工，Remote Desktop Commander只作失效備援；本機Codex可直接檔案/Git/測試。每次以當前工具schema發現功能，先runtime_status/work_on_project定位，不沿用舊session ID。先核對repo/HEAD/dirty/build，再讀AGENTS與本文件；只回傳bounded diff/log tail。備援前查舊job避免雙writer。finish snapshot是輔助，不代替exit code／測試／push／CI。

保持quote-only，不登入或重啟既有recorder、不下單／查帳戶部位／拷貝密鑰，不改其他專案。已授權工作包內自行修正常規問題；使用者中途補充不代表取消任務。未完成／資料不足／尚未驗證清楚分開。每包更新repo交接與來源快照、提交推送程式文件，不上傳私有行情／DB／模型權重。PR不自動merge；遠端不可用才提供可回貼備援prompt，不能假裝已施工。

若需OpenCode回貼，只在兩遠端工具不可用時採用；先查官方 https://opencode.ai/docs/ 與實際模型列表。使用者曾稱的DeepSeek版本/high/max不是已驗證API名稱，不杜撰設定參數。
