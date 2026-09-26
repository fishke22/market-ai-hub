# MARKET_AI_HUB 後續建設規劃

版本：2026-09-24。性質：供使用者採用的規劃；不是把全部 backlog 一次授權執行，也不是模型有效性的保證。沿用正式 V2 freeze，不重新命名既有 phase；以下 W0–W8 只是本交接包的工作包編號。

## 本輪完成狀態

W0 與 W1 的核心根因修補已在程式完成，詳見 03；不用再照舊稽核重做。2026-09-25 W2 離線工程契約已完成三段：① field-aware quote reader/replay → V2-A.2 + V2-H lineage；② canonical Feature Store provenance/model-feature gate → public packet；③ cutoff/lineage/contract/frequency-aware model-input boundary。標記 **W2_OFFLINE_CONTRACT_PASS**，但不是 DATA READY：現場 recorder 仍 RUNTIME_ADOPTION_PENDING，broker TICK 與現有 1d 模型頻率不相容，且沒有驗證 daily bar aggregation。W1 的 reconnect/roll/crash durability/長期壓測仍未驗。下一優先是 W3 到期/scope/as-of correctness；必須先於 W4 fitting。

## 1. 成功如何衡量

第一優先是「資料正確、預測可追溯、失效時會停止宣稱可信」，再追求相對簡單基線更好的實際預測。準確度依任務量測：點預測 MAE/RMSE/MASE，分位數 pinball，分布 CRPS/區間 coverage 與 width，事件 Brier/log loss/reliability，經濟層則使用含成本與滑價的淨績效。不得以單一方向勝率或測試總數代替全部品質。

每個 target family × instrument/contract semantics × horizon × event family × model version 都要有自己的成績與資料樣本。沒有足夠證據時允許 baseline、WAIT 或 abstain，這是正確輸出。

優先路線：W0 → W1 → W2 → W3 → W4 → W5 → W6。W7 可在 W1 路徑修正後獨立進行；W8 是最後交付。若 live feed 暫時不可用，繼續離線 replay/契約/工具工程，不假造行情。

## 2. 工作包與驗收

### W0：接手目前工程並修正狀態

輸入：實際 AGENTS/bootstrap、dirty diff、元大 guide/matrix/recorder、V2-H/I contracts、稽核文件。

工作：確認是否有另一個 agent 正在改相同檔案；保留所有已存在修改。把已發布 `d649059` 與未提交功能區分。更新 handoff 的過期 Last updated、project-status 頂部與歷史 NEXT；將 static provider capability 與當前 runtime freshness 分開，不把 static 常數當 live health。

验收：所有「目前」文件與 machine-readable 狀態語義一致，舊報告保留日期；同一入口能說明哪個功能在 main、哪個在 branch、哪個仍未驗證。這一棒不建新模型。

### W1：可靠行情錄製與公開機率邊界

按稽核 H1–H5 優先處理。先用離線 replay 建反例；不得為了測試再次登入現有 recorder。

1. 持久化使用有界 queue/受保護批次；只有成功寫入及提交後才 ack，失敗保留可恢復資料與告警。不得吞 OSError。Parquet 先暫存後原子發布，manifest 記錄筆數、時間區間、雜湊、schema、成功/失敗批次。至少定義 crash 可接受損失窗口；若要求零遺失，須 durable spool/WAL 且配額管理，不能只靠 RAM。
2. CLR callback 與寫檔工作分離；bounded diagnostics（現有 `_callbacks` list 不能無限長）。壓力超限有 dropped/backpressure counters，不以凍結桌面作代價。
3. 單一實例由程序級原子 lock/mutex 保護整個生命週期；PID/status 是觀測，不是互斥。兩個同時啟動只允許一個擁有連線。不能僅因 PID 存在就判定健康。
4. 每欄資料有自己的 as-of；接收新買價不能刷新舊成交價時間。分離 heartbeat、last-any-callback、last-valid-trade/bid/ask、connected、subscribed、freshness。休市與缺 callback 分開。
5. 訂閱有總量/單批/速率上限、action whitelist、不可逃出資料根的 control 路徑、atomic request 寫入、idempotent request ID 和結果原因；unknown action 不默認 subscribe。
6. 合約到期、roll、日夜盤切換需常駐程序重新評估，不能僅啟動時解析。來源無法確定時間/日期就 UNKNOWN，不補假的 exchange timestamp。
7. 校準公開判定必須驗證真正證據與 scope/版本/有效期間，數字有限且在 [0,1]。CLASS_SCORE 保持 score；校準之後另建 EVENT_PROBABILITY artifact 連回原 score，不改寫歷史。

驗收：磁碟滿/寫入拒絕/程序 crash/雙開/回呼洪水/錯商品/亂序/零回呼/斷線/過期合約/無效要求/偽造校準證據均有可重現測試；所有錯誤會留下 truth 狀態。現場重啟若有必要，先安排安全交接與明確授權，保留舊版回復路徑。

### W2：把已錄製行情接入資料契約

沿用 `runtime_paths`、V2-A.2 session/factor routing、2H.2 audit DB，不建立平行資料真相。

輸入：通過 W1 的來源批次和免費/已合法取得的歷史來源。新增 typed reader/adapter，將 quote events → FactorRepresentationObservation → immutable snapshot → feature store。記錄 event time、received_at、available_at、timestamp precision、venue session、trading date、contract month、roll、currency、tick/multiplier、source snapshot IDs。

資料品質：處理零/負/NaN/Infinity、累計量重置、價格縮放、成交與報價差異、時鐘偏差、重複/亂序、斷線缺口、收盤與 settlement 差異。先做歷史 replay，再做每個市場的受控 observation。已有日線資料不能被改名成真實 tick/1m；bid/ask callback 也不自動代表有完整 L2。

验收：同一 snapshot 重播結果一致；跨市場/跨合約不能混用；stale/unknown 不進需要 live 的特徵；MCP public packet 能追到來源；契約缺欄會 typed reject。明確證明 recorder → 模型輸入，而不是只有新 JSON 檔存在。

### W3：真實預測、到期結算與前向樣本

**2026-09-25 狀態：W3.1 governance + W3.2 precommitted forward-cycle engines PASS；actual forward evidence 仍 NONE_YET。** 2H.3 已把 sample origin + label window 綁入 prediction identity；W3.2 已固定 OSAKA_MICRO/JNU 1-session baseline 的 precommit/settlement 時序與 Feature Store 契約。現場仍缺合格的 contract DAILY/PIT-safe input，所以沒有真實 forward prediction 被建立。

建立最小的可運作研究循環，先一個直接商品、一個 horizon、一個簡單 baseline，再依同一契約擴展到各市場族群。不能把每個 callback 當獨立預測樣本。

forecast origin 前封存 prediction、model/version、完整參數、feature cutoff、source IDs、forecast artifact、event/zone policy；horizon 到期後另存 outcome。預測 horizon 必須能解析實際 label window；`outcome.available_at >= forecast_origin` 單獨不足以證明到期合法。修訂用 supersedes，新版與原版都可追溯。

2I.1 指標引擎仍只吃 audit DB，現在由 2H.3 + W3.1 governance 先決定 eligible samples；evaluator 仍不能直接補 CSV。歷史來源可經合法 ingestion/replay 建立 audit artifact，但標為 `RETROSPECTIVE_REPLAY`，與真正預先封存的 `FORWARD_PRECOMMITTED` 分開；基礎模型訓練 cutoff 不明時揭露預訓練重疊風險。

工程驗收已通過：未到期、evaluation_as_of 後才可得 outcome、未知來源、重複樣本、錯 model/version/event/label scope、錯 artifact pairing / superseded selection 會拒絕或排除；W3.2 另拒絕不具 PIT/source/contract/roll provenance 的 daily input、錯 precommit 時點與跨合約 settlement。**尚未完成的是 dedicated contract DAILY terminal-close feature 的真實來源與 forward 樣本自然累積，不得用 synthetic 測試代替。**

### W4：校準與外樣本治理

先在看結果前凍結 protocol：chronological train → calibration → validation → untouched final OOS；rolling/expanding folds，以標籤重疊長度 purge/gap，不能用 random split 或僅按行數假定時間獨立。模型選擇、特徵處理、ensemble 權重與校準 fit 都不可看 final OOS。

先比較基準頻率、未校準輸出與簡單 sigmoid calibration；資料足夠才考慮 isotonic。不是盲目套 sklearn 預設 CV；需要符合時間序列的明確切分。

報告 Brier/log loss、reliability、每 bin count/不確定性、calibration slope/intercept（适用時）、區間 coverage、按 regime 的穩定度。Brier 下降不單獨證明校準更好。稀有事件要兩類樣本和足夠時間跨度；不能硬訂「滿兩筆即可信」。接受門檻以預註冊精度/CI、相對 baseline、樣本有效性決定，禁止看結果後修改門檻。

校準產物綁定 dataset ID、訓練及校準窗口、holdout 結果、model/target/horizon/event/policy/version、有效期、drift 狀態。只對滿足相同 scope 的 public probability 放行；過期/漂移/缺證據即 abstain。校準原生合理的模型也須獨立驗證，不能因未 fit 校準器就亂加處理。

验收：2I.1 原語義保持；新 fitting 層有正式契約與新版本；證據從受控流程生成，不能手填 `CALIBRATED`；final OOS 只消耗一次，不反覆選模型。多模型/多 zone 搜尋要記 trial ledger 與多重比較控制。

### W5：Price Map + Probability Map

沿用 `research/price_probability_map.py` 和 `config/zone_policy.yaml`。先完成 terminal distribution，再依資料能力建立 path event。Phase3B.1 目前 deferred，必須先核對 V2 foundation gate，採用正式變更流程後才解除。

| 輸出 | 定義與限制 |
|---|---|
| 中心 | 明確是 mean、median、mode 或版本化 research center，不能混稱 |
| Buy/Neutral/Profit zones | 在預測前凍結的研究區界；不預設 q10=買點、q90=賣點；做多/做空語義分開 |
| terminal | horizon 終點落在指定区間的機率；互斥且完整分區才應總和為 1 |
| touch | 期限內曾觸及指定邊界/區域；兩側都可能碰，機率不能被迫加總 1 |
| first-passage | 先上界、先下界、皆未觸及；同 bar 雙觸及但缺順序資料標 AMBIGUOUS，不猜 |
| break / acceptance | 超越幅度、持續時間、收盤確認等規則版本化，與 touch 分開 |
| Model Failure | 特定預測假設失效、輸入 stale、品質/漂移失效分開，STOP 不代表 SHORT |

三個 quantile 不能還原完整 distribution，更不能推出 path probability。有 sample paths 仍需時序依賴、資料頻率、來源、樣本數與各 event family 的實測校準；以獨立 terminal 抽樣拼路徑容易產生虛假觸及率。

skewness/fat-tail/多峰/regime 可以先作描述性診斷；附方法、樣本與不確定性。模型間分歧不直接等於市場多峰，常態不成立也不自動證明厚尾。少量樣本不穩定則 UNKNOWN。HMM、survival/competing risks、change point 等留 challenger，不為了名字完整全部安裝。

验收：target/horizon/event 一致、分布 provenance 完整、概率邏輯一致、缺資料不輸出百分比；路徑事件有 bar ambiguity、censoring、未觸及樣本的測試。

### W6：Reward/Risk、情境及白話層

R/R 由同一情境的可能收益與損失計算，注明幣別、multiplier、entry 假設與成本。高 R/R 不等於正期望值；有中途退出、timeout、gap、兩側都觸及時，要用完整 exit policy，不套不適用的二元勝率公式。

維持 OOS/forward 的 baseline/策略比較，加入 spread、滑價、fees、roll cost、成交可行性、最大回撤、tail loss、turnover、時間穩定度。若沒有正的穩健淨優勢，輸出 NO_ECONOMIC_EDGE；不能因底層預測偏多就推薦追價。

LLM 使用 compact safe packet：每項數字附可追溯 field/source ID；數值由程式計算，LLM 只解釋。先 deterministic template 再生成自然語言；不引入昂貴多 agent 評審作必要依賴。至少檢查 stale quote、proxy/direct、校準不足、模型分歧、無效合約、日夜盤、未知 first-passage 七類情境，任何會捏造機率或交易指令的輸出都拒絕。

示例（只是格式，不是真實行情）：
> 目前價格位在本次研究區間下半部。系統已有價格範圍估計，但尚無通過驗證的路徑機率，所以不能說「上方一定更容易先到」。若資料停止更新或進入預先定義的失效狀態，這次判断需重新計算。目前以觀察與情境比較為主。

有證據後才允許：「根據某 model/version、某 horizon、N 個有效樣本與指定驗證期，上側先觸及機率為 …，估計誤差 …；若 … 則失效」。不能為符合使用者期待省略 N、期間或限制。

### W7：可移植重建與資料備份

目標分層：

1. **同機換硬碟**：source/config/data 使用相對根目錄；新路徑重建 venv，重新產生 MCP client 路徑及 Startup/排程。舊位置不可再被新程序存取。
2. **新 Windows**：合法安裝 Python/.NET/VC runtime/必要 x86 sidecar，重新註冊 SDK/COM 與個別建立 WinCred/憑證。不得把另一台的秘密複製到公開包。
3. **離線重建**：可選 wheelhouse、鎖定依賴、各平台可用 wheels、模型 revision/hash；只有許可的依賴才可打包。無授權/不適用的 SDK 或權重提供官方取得步骤。

沿用 `project_root()`/`runtime_paths`；所有 recorder PowerShell 腳本也必須遵守 `MARKET_AI_DATA_ROOT`。明確定義相對 override 相對誰解析。source checkout 現用 `parents[3]`，若要支援 wheel install，須另驗證 config/package resources，不能把 editable install 成功當一般安裝成功。

Python 官方指出 venv 一般不能搬移，需於目的地重建：https://docs.python.org/3/library/venv.html 。所以產品承諾是「不用手改程式路徑」，而非「所有依賴不需任何設定」。

安裝程序每個外部命令檢查 exit code；下載固定版本並保留來源與雜湊，保留 TLS。CPU core 與 optional GPU/models/broker 分層驗收；欠缺帳號時 core 應可用，quote 層清楚标 BLOCKED。

備份不能只複製正被寫入的 DB/Parquet。使用既有備份流程或一致性 snapshot，驗證 WAL/交易一致性、checksum、row counts、prediction IDs；做 restore drill。公開 GitHub 只備份程式與可公開文件，PRIVATE data 做本機或使用者明確核准的私人備份。

验收矩陣：另一個本機目的地 + 空白/中文路徑 + 非 repo cwd + 外部 DATA_ROOT + 新 venv + 無 D 槽/原路徑不可用的測試環境。不要為測試卸載磁碟或破壞原系統。每格分别列 core/MCP/models/quote/research，不以 core PASS 代替全功能 PASS。

### W8：發布與交接閉環

每個成功工作包都更新已有 docs/tests，再做秘密掃描、文件連結、已修正的 CI profile、必要回歸。依 repo 慣例 commit/push/PR；檢查 remote SHA 與 CI，合併後重新驗證。只有真正發布版本才 tag/release，不每修一個文件就升版。

回報狀態：IMPLEMENTED_PENDING_TEST → LOCAL_PASS → PUSHED → PR_CHECKS_PASS → MERGED_POSTMERGE_VERIFIED。遇到保護規則或帳號權限問題，保留 LOCAL_PASS_REMOTE_PENDING，附精確阻塞點；不繞過。

保留穩定 rollback commit，schema migration 有 backup 與 replay 驗證，不破壞 append-only audit。然後產生最新上下文快照供上傳，資料來源刪除/標註過期版，下一棒不需要重讀所有歷史長報告。

## 3. 免費來源與官方參考

下列文件/程式來源可免費閱讀；資料使用仍以來源條款為準。查核日 2026-09-24。沒有推薦新的付費供應商，沒有取得新的付費訂閱。

| 資源與連結 | 用途與界線 |
|---|---|
| [TWSE OpenAPI](https://openapi.twse.com.tw/) | 官方公開 API 入口；日線/公開資料，不視作無限制 tick feed；此回合頁面為 Swagger，未實测各 endpoint |
| [TAIFEX 每日交易行情](https://www.taifex.com.tw/cht/3/futDailyMarketReport) | 官方免費網頁查詢與日行情核對；不是完整永久免費 tick 庫 |
| [FRED API](https://fred.stlouisfed.org/docs/api/fred/) | 總經時序，API key 與各 series 授權另核對；不是所有資料都屬美國政府無著作權 |
| [ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html) | 初次發布/後續修訂 vintages，補 as-of 回測的重要缺口；不能用今日修訂值冒充過去資訊 |
| [Chronos 官方程式](https://github.com/amazon-science/chronos-forecasting) | 沿用既有免費開源模型；固定程式與權重 revision，不能據 model card 宣稱金融優勢 |
| [TimesFM 3.0 官方模型卡](https://huggingface.co/google/timesfm-3.0-pytorch) | 本次確認 non-commercial license；免費取得不等於可商用或任意再散布 |
| [scikit-learn 校準](https://scikit-learn.org/stable/modules/calibration.html) | 使用既有依賴設計獨立 calibration 與可靠度評估；避免把 Brier 當單獨校準證明 |
| [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | 時序切分參考；標籤重疊 purge 與真實時間間隔仍需本專案處理 |
| [Python venv](https://docs.python.org/3/library/venv.html) | 跨硬碟以重建環境為正式路線；專案目前 Python 3.11/3.12，相容性依鎖檔驗證 |
| [元大 SPARK](https://www.yuanta.com.tw/file-repository/content/API/page/index.html) / [文件](https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/index.html) | 免費公開文件與官方元件入口；需帳號權限，不能承諾各交易所資料免費或可訓練/再散布 |
| [元大期貨 API](https://www.yuantafutures.com.tw/ytf/easywin/api/download.html) | 行情與交易元件分開；本專案只用行情；公開頁 2.1.2.7 不等於本機元件版本 |
| [ChatGPT Projects](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) | 專案指令、資料來源與記憶；檔案快照仍需更新 |
| [Desktop Commander](https://desktopcommander.app/) | 官方描述支援 ChatGPT 遠端讀檔/命令；Remote 配額與現有訂閱另計，不能保證無限免費或一定省 token |
| [OpenCode Models](https://opencode.ai/docs/models/) / [Agents](https://opencode.ai/docs/agents/) | 核對 Desktop 的實際 provider/variant 與 Build/Plan 工具權限；本次沒改本機 OpenCode 設定 |
| [DeepSeek 官方更新](https://api-docs.deepseek.com/updates/) | 2026-09-10 記載 V4.1 Flash 官方 ID 為 deepseek-flash，舊 alias 暫時路由到新版；自訂 provider 是否相同仍需實測 |

DeepSeek 官方更新也記載 low/high/max 思考層級；使用者要求的 high/max 可作偏好，但 OpenCode 能否傳遞取決於實際 provider/SDK/version。thinking-mode/API 詳頁本次擷取失敗，因此不提供臆造的 OpenCode JSON 設定。LLM API 與 Remote 工具既有使用成本不屬於「免費資料來源」承諾。

J-Quants、FinMind、Yahoo、225LABO 均已在 repo 有相關路徑/限制；本規劃不增加其付費用量。特別是 OSE 完整歷史、L2、逐筆成交沒有經本次查核證明存在完全免費且可合法長期保存的來源；不足則把功能留 DATA_DEPENDENT。元大接收成功也不自動給予模型訓練、跨機分享或公開再散布權。

## 4. 建議先不做

先不加更多 LLM 層、向量記憶庫、微服務、Kubernetes、全模型自動微調、L2 order-flow、永久常駐重訓。現有檔案交接、單一可靠 recorder、可追溯 audit DB、幾個基線與真實前向證據已足以解決目前最關鍵問題。

擴充條件：只有當對應資料/樣本/硬體/授權已具備，且在預註冊 OOS 能證明增益，才把 challenger 納入正式研究。不能因高價模型或較長 reasoning 就假設金融預測更準。
