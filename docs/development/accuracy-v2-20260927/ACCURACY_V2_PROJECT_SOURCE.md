# MARKET_AI_HUB Accuracy v2：預測能力提升與施工契約

## 2026-10-01 可替換快照：JNU closed-window rollup

- 真實 immutable dataset 已有 2 筆 CLOSED rows，兩筆都逐筆用 governed summary 重建並取得相同 canonical hash，沒有資料漂移。
- 第一段為 18:13:21–18:58:21 Asia/Taipei，因 owner degraded 關閉，且 baseline 在中途才採用；第二段為 22:08:35–23:13:21，window-start baseline 完整。2026-10-01 觀察到 `NO_RUNNING_OWNER` 與 stale heartbeat 後，只把第二段封在舊 `last_healthy_at`，沒有啟動/重登 recorder，也沒有把今早時間假裝成昨晚關機時間。
- 新增 `research/jnu_capture_window_rollup.json` 與繁中 markdown；以 `session + session_start_date` 分組，因此現在的 **2 windows 只算 1 個 2026-09-30 NIGHT market session**，禁止把 PC 開關切段當獨立樣本數膨脹。
- live rollup：109.77 verified capture minutes；1 個完整 baseline、1 個中途 baseline；microstructure verified=2/2；dropped=0；persistence error=0；broker action=0；FULL_SESSION_LABEL_READY=0。
- JNU2612 capture trades=8,393 / DealVol=48,376 / volume-weighted VWAP≈67,555.38；JNU2703=260 / 388 / ≈67,775.46。只屬 capture/context 品質，不是方向準確率或OOS增益證據。
- source rows hash=`5d37db2a67ad912b4d5a2a8bb9f1e42a0742db9a3ef2075efd031155260c7b2c`；focused regression=`45 passed, 1 deselected`；build=`a0ac8fdb8f218c39`；predictive/calibrated/edge claims 仍 false。


## 2026-09-30 可替換快照：append-only JNU closed-window dataset

- 新增 `research/jnu_capture_window_dataset.json`，只收 **CLOSED verified capture windows**；ACTIVE window 絕不提前定案。
- coverage ledger 每次 verified healthy sample 都保存 `session_context_latest`，research summary 對 closed window 固定使用 `INTERVAL_LAST_VERIFIED_HEALTHY`。因此同一官方夜盤之後重新開機、繼續收到新 tick，也不能回頭改寫舊 capture window 的 latest/context/label 狀態。
- dataset 以 `window_id` 做 semantic append-only；既有 row 若遇到不同內容，回報 `IMMUTABILITY_CONFLICT` 並保持檔案不變。沒有 interval-local snapshot 的 legacy closed window 不升格入庫。
- 實機目前 window 仍 ACTIVE，因此 dataset 已建立但 `row_count=0`；這是正確結果。等未來 watchdog 看到 >8 分鐘 gap，舊 window 只在舊 `last_healthy_at` 關閉後才 append 第一筆。
- recorder PID 仍 16204；focused regression=`41 passed, 1 deselected`；build=`a0ac8fdb8f218c39`。不改 predictive/calibrated/edge claims。


## 2026-09-30 可替換快照：JNU human-readable live brief

- watchdog 現在從 governed capture-window summary 自動產生 `research/jnu_live_capture_brief.json` 與繁中 `research/jnu_live_capture_brief_zh_tw.md`，不另掃全量 Parquet，因此沿用相同 no-backfill / window-delta 語義。
- 給非技術使用者的 brief 會直接說明：目前錄製中或已結束、verified window 時間、差分基準是否覆蓋整段、microstructure/drop/persistence 健康、每個 JNU 合約的 window trades/DealVol/VWAP，以及明確標成 session-level 的最新價/range/VWAP context。
- brief 會用繁中列出 full-session label blockers、目前可做的研究與不能宣稱/不能做的事項；硬鎖 `predictive_gain=false / calibrated_probability=false / trading_edge=false / order_action=false`，不產生個人化進出場/部位/下單指令。
- 約 18:35 Asia/Taipei 實機仍為 PID 16204、microstructure verified、dropped=0、persistence_error=null。基準 18:27:23 晚於 window start，因此 brief 明寫不倒算。當時 JNU2612 window delta=652 trades / DealVol 3446 / VWAP≈67,196.14、session latest=67,210；JNU2703 delta=26 / volume 43 / VWAP≈67,424.19。只屬 descriptive/context。
- focused regression=`37 passed, 1 deselected`；build=`a0ac8fdb8f218c39`。


## 2026-09-30 可替換快照：JNU capture-window research summary

- 每個 verified capture window 現在記錄 materializer counter baseline/latest，研究數值採**視窗差分**，不把開機前的整個夜盤累積誤算進 18:55–22:00 或其他實際開機區段。
- 新 window 在 verified start 建 baseline；若功能上線時 window 已經進行中，僅從上線時採 baseline，並標 `metrics_complete_from_window_start=false / BASELINE_ADOPTED_AFTER_WINDOW_START`，不倒推或補造早先資料。
- 5 分鐘 watchdog 同步寫 `research/jnu_capture_window_summary.json`：exact start/last healthy/close、前一 verified window gap、observed minutes、window trade/DealVol/VWAP/new 5m bars、microstructure callbacks/drop/persistence、session profile availability、以及 open/close boundary label blockers。
- session price/volume profile 若非 window-specific delta，只能標 `SESSION_CUMULATIVE_CONTEXT_NOT_WINDOW_SPECIFIC`；partial window 仍可研究，但不得升格 predictive gain/calibrated probability/trading edge。
- 下次開機若健康樣本 gap >8 分鐘，舊 ACTIVE window 在舊 `last_healthy_at` 關閉，新 window 從新健康樣本開始；不把重開機時間假裝成前次關機時間。
- 實機 recorder PID 維持 16204。既有 window 於 18:27:23 才採第一個新 baseline，因此誠實標 incomplete-from-window-start；約 34 秒後差分為 JNU2612 +24 trades / DealVol +101 / VWAP≈67,178.86，JNU2703 +2 trades / DealVol +5。focused regression=`35 passed, 1 deselected`，build=`a0ac8fdb8f218c39`。


## 2026-09-30 可替換快照：JNU variable-PC capture windows

- 使用者不會整夜開機。平常約 18:55 開機、約 22:00 關機，但可能提早或延後；此時段只作慣用參考，不是硬門檻。系統必須在實際開機期間自動抓取，不能要求整夜維持電腦。
- 既有 5 分鐘 watchdog 現在同步維護 `automation/jnu_capture_coverage.json`。只有 `SAFE_DEFAULT_OWNER_HEALTHY` 算 verified capture interval；健康樣本間隔 >8 分鐘就切新 window，degraded/unverified 會結束 verified window；缺失時間絕不 backfill。
- 有真實 tick 的不完整區段保留為 `PARTIAL_WINDOW / usable_as_context=true`，可供 5m/VWAP/profile/微結構/context 分析；不因沒有官方 session open/close 就丟棄。只有 materializer 真正觀察到 open+close boundary 才升格 `FULL_SESSION_LABEL_READY`，完整 session 是 opportunistic，不是日常開機要求。
- 實機施工未重啟 recorder：PID=16204、owner healthy、runtime/disk build=`a0ac8fdb8f218c39`、無 independent owner、無 broker action。focused coverage/watchdog regression=`31 passed, 1 deselected`。
- 每次施工回報結尾固定寫清楚：現在繼續或停止、下一步、是否需要使用者新授權。


## 2026-09-30 可替換快照：zero-cost JNU live evidence path

- 使用者新增永久硬限制：**永不付費**，並要求假設永遠不建立 AWS 帳戶時系統仍可達成原始目的。因此 AWS/EventBridge 降級為 optional；本機 Windows Task Scheduler、既有 GitHub/public-source fallback 與 quote-only SPARK 才是預設 continuity path。雲端缺席只影響 punctuality/availability，不得阻塞本機 forward/context evidence 累積。
- `MARKET_AI_HUB_JNU_Capture_Watchdog` 已由舊 18:55–22:00 wrapper 改成 source-controlled 每 5 分鐘 task（Interactive/Limited、StartWhenAvailable、IgnoreNew），action=`ensure_jnu_data_capture.ps1`。2026-09-30 16:33:18 Asia/Taipei 由 Windows Task Scheduler 自行恢復 single owner，preflight=`SAFE_DEFAULT_OWNER_HEALTHY`，沒有 duplicate owner、沒有 broker action。
- quote-only bounded reconnect 正式 live adoption：`yuanta_live_recorder.yaml version=2026-09-30`、`auto_reconnect.enabled=true`、max_attempts=3、bounded backoff；仍是 full-runtime replacement，且與 tick-detail maintenance 互斥。
- 新增／接續 `JNU.SESSION.MATERIALIZED.2`：StockTick callback 直接增量物化 exact-contract DAY/NIGHT session、5m bars、DealVol/trade count、VWAP、range/profile、MFE/MAE、boundary coverage。只有 open+close boundary 都觀察到才 `label_ready=true`；partial session 不得回填、不得升格正式 label。
- 今日主機晚於 16:00 開盤才可用；JNU2612 first retained night event=16:05:53 Asia/Taipei，所以 `open_boundary_observed=false / coverage_complete=false / label_ready=false`。16:33 descriptive snapshot：577 verified StockTick trades、DealVol=2435、range=67,350–67,510、VWAP≈67,413.46；只作 live research context。
- 修正 live materializer freshness race：production live call 用實際 artifact read time 評估 freshness，顯式 `now=` replay 維持 pinned。修正前可能因 concurrent persist 產生負 age 而誤判 STALE；修正後實機=`FRESH / used=true / fallback_to_bounded_parquet=false`。
- build=`a0ac8fdb8f218c39`；驗收：focused `30 passed`、build-freeze `3 passed`、affected selector `107 passed, 1 deselected`。不重跑 full suite。維持 `PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false`，無 account/position/balance/order action。


版本：2026-09-27 Accuracy v2。文件性質：研究與施工規劃＋可替換實作快照。**P0/P1/P2/P3-A/P3-B/P4/P5/P7 已完成目前可施工的工程落地；P2 development 是 NO_IMPROVEMENT、保留 baseline；P3-A past-only covariate 工程 PASS；P3-B 已取得 REAL receipt-time-causal P1 DATA_READY packet；P4 已讓系統在沒有新 forward outcome 時仍能以 baseline＋波動＋conformal區間＋拒答作有效分析；P5 forward monitor 與 P7 independent-engine acceptance 已完成工程，但未把 development interval、quantile challenger、forward monitor 或 execution parity 冒充預測增益／校準機率／交易 edge。P6 保持 conditional，不是工程 closeout blocker。** 本文件取代同日 vNext 的模型優先序與下一包設計；保留既有修復、資料治理、quote-only、安全與搬移規範。不要並列兩份互相矛盾的「最新版」指示。

## 2026-09-28 P5 first-origin operational evidence + clock hotfix

- First canonical window 2026-09-28 08:05 Asia/Taipei did **not** produce a canonical artifact. One-shot automation had a run record at 08:08, but later audit remained canonical_prediction_count=0. Manual recovery at 08:17 was still inside the frozen <=15m lateness gate.
- Root cause: `run_p5_cycle()` froze `as_of` before public-source collection. The collector then rewrote the current official JPX settlement parquet, whose file mtime is the observed receipt timestamp; that receipt therefore became a few seconds later than the frozen origin and correctly failed PIT validation as `REFERENCE_RECEIVED_AFTER_ORIGIN`. A further retry was blocked by the existing two-attempt daily cap. No state reset, backdating, manual ledger insertion or gate bypass is allowed; 2026-09-28 remains a genuine missing canonical origin.
- Hotfix re-anchors production actual decision time after collection while preserving explicit `now=` for deterministic replay/tests. Nominal publication+5m origin, <=15m lateness, receipt-before-actual-origin, append-only audit, max attempts and no-backfill semantics are unchanged. source/config build=`426583a3e6f2f27e`.
- The separately authorized 07:45 JNU intraday StockTick/FiveTick trial succeeded using the existing healthy single-owner recorder; it is receipt-time `CONTEXT_ONLY_NOT_P5_FEATURE`, not a preregistered P5 feature and not forward evidence.
- `PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false` remain frozen. This hotfix repairs operational causality only; it does not manufacture the missed sample.
- Validation：focused P5=`12 passed`；final targeted P5/protocol/build-freeze=`67 passed, 2 deselected`；diff-check PASS；changed-file secret scan=0 hits。

## 2026-09-28 C23 terminal-close operational miss / evidence boundary

- 2026-09-28 OSE post-close C23 reached the frozen three-attempt daily cap without typed terminal-close evidence. No counter reset、fourth attempt、manual materialization or backfill is allowed. Current state=`BLOCKED / ATTEMPT_LIMIT / 3`.
- Operational causes were engineering races/gates, not missing market prints: (1) stop script may emit `STOPPED` just before the old Python PID fully exits, so C23 now waits for preflight=`NO_RUNNING_OWNER`; (2) a fresh post-close maintenance owner may be `DEGRADED` solely because there are no new streaming callbacks. The tick-detail helper now allows this exact state only when heartbeat is fresh, runtime/disk build match, runtime measurement gate=true, tracked gate=false, and the sole allowed health reason is `NO_RECENT_CALLBACK_SESSION_UNCHECKED`. Other degradation remains fail-closed. Regression=`25 passed, 1 deselected`.
- Separate continuous StockTick preservation is research-only: JNU2612 07:45–14:45 Asia/Taipei has 64,882 deduplicated ticks、DealVol=295,142、O/H/L/last=66,200/66,840/65,600/65,600、VWAP≈66,206.416. The observed 15:45:01 JST tick is 65,600 with DealVol=2,289、bid/ask=65,595/65,600、receipt lag≈0.185s. It is `RESEARCH_ONLY_NONCANONICAL_NOT_C23_TYPED_EVIDENCE` and cannot establish terminal-close DAILY evidence or settle/promote W3.2 by itself.
- `PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false` remain unchanged. No account/position/balance/order action occurred.

## 2026-09-28 Live acquisition / authorized recorder handover

- 使用者已明示授權 runtime handover；Yuanta quote-only single owner 由 stale build `2647d9da4e9b73ac` 切換到 current build `426583a3e6f2f27e`。最終 preflight=`SAFE_DEFAULT_OWNER_HEALTHY`；JNU2612 receipt lag 由約 1162s backlog 降至 latest≈0.73s / median≈0.26s / p90≈1.18s，StockTick/FiveTick live verified，dropped=0、persistence error=null。
- 今日實際可得 context：JNU2612/JNU2703、NQ/MNQ、ES、JPY futures、Gold、WTI、DXY、VX。ZF/ZN 回傳不可用 sentinel，明確排除。2026-09-28 TWSE/TAIFEX 為官方教師節休市，沒有新的台灣交易樣本；stale cash snapshot 不計入。
- JPX settlement refresh latest=`2026-09-25`，Jul-Sep archive 無 missing day；JPX derivatives investor-flow 最新公開 receipt=`20260907/20260911`、product code=331、receipt-time only。C23 2026-09-28 已完成窗口內嘗試但因上方所述 operational gates 用盡三次上限，typed terminal-close evidence=`BLOCKED / ATTEMPT_LIMIT / 3`；P5 2026-09-28 missed origin 不回填。
- `request_yuanta_quote.ps1` / `request_yuanta_tick_detail_measurement.ps1` 修正空 `health_reasons {}` PSCustomObject 被誤算為一個 health reason 的 false block；真正 health reasons 仍 fail-closed。Live quote request 已成功驗證，PowerShell parse PASS，final Yuanta+C23 regression=`24 passed, 1 deselected`，並補 static regression guard。

## 2026-09-28 System engineering closeout

- 新增 `AV2.SYSTEM_COMPLETION.1` / `accuracy_v2_engineering_closeout_v1`，由 `config/accuracy_v2_system_completion.yaml` + `system_completion_snapshot()` 固定「目前可施工工程」的完成定義。它不把 future canonical outcomes、Taiwan 新 observation periods、外部 provider 設定、未授權 runtime/order execution、sealed final 或 P6 conditional research 冒充工程缺口。
- Current closeout snapshot：required engineering=17、actionable gaps=0、status=`ENGINEERING_COMPLETE_WAITING_FOR_EXTERNAL_EVIDENCE`。MCP 新增 `get_system_completion_status`；`get_system_info`、Capability Registry、`validate_accuracy_v2_system.py` 同步輸出 closeout truth。Static `system_manifest.yaml` / `capabilities.yaml` 亦同步到 27 MCP tools 與目前 first-class source status。
- TAIEX direct reference 補成 TWSE 官方 `MI_5MINS_HIST` daily OHLC；AnalysisPacket 先用官方 TAIEX cash close，失敗才降級 `^TWII` proxy。2026-09 live smoke=18 rows，latest 2026-09-24 OHLC=48,075.39 / 48,117.54 / 47,754.72 / 48,024.60。TAIEX cash index 不可成交；TX/MTX/TMF execution validation 與 historical OOS evidence 仍各自未成立。
- JPX Trading by Type of Investor 接上官方 2026-04-23 後 weekly CSV；Nikkei 225 Micro product code=`331`，以同週官方 PDF/CSV aggregate reconciliation 驗證。Latest live receipt smoke period=`20260907/20260911`、11 volume rows。CSV 無 exact publication timestamp，因此 `available_at` 固定 actual retrieval time；不得 retroactive historical PIT backfill，也不自動成 predictive feature。
- 修正 AnalysisPacket 既有 target-semantics overwrite：session/freshness/reference-role metadata 現在 merge-preserve；settlement / FinMind / TWSE official dated references 都標 `DATED_OFFICIAL_REFERENCE`，不再錯標 proxy。
- Deferred/non-blocking 明列：P6 CUSUM/Page-Hinkley/BOCPD/state-transition probability/fine-tuning adapters=`DEFERRED_CONDITIONAL`；broker/order execution=`PROHIBITED_NO_AUTHORIZATION` + quote-only；optional external macro sources=external config/source dependent。這些都不改 `PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false`。
- Final clean-tree source/config build=`2647d9da4e9b73ac`。Acceptance：focused closeout=`124 passed, 4 deselected`；cross-layer/build-freeze=`193 passed, 7 deselected`；MCP stdio=`27 tools / missing=0 / PASS`；system readiness=`READY_FOR_ANALYSIS_AND_GOVERNED_PREDICTION`。EOF-only completion-YAML normalization 前的內容等價 build full offline（只排除既有 recorder owner-mutex）=`2213 passed, 1 skipped, 24 deselected, 152 warnings in 286.83s`，exit 0；該格式正規化只改 byte fingerprint。最終 build 另以 build-freeze=`49 passed, 2 deselected` 及 exact CI-equivalent selector=`2202 passed, 1 skipped, 35 deselected, 130 warnings in 251.44s`，exit 0 驗證。
- 後續不是「補施工」：P5/Taiwan 必須等真正新的 future observations；P6 只有在預先規定的 data/runtime/independent-gain prerequisites 存在後才另開；scheduler、runtime handover、live execution 需另行明示授權；HPQ1 old final 與已曝光 final 不重跑、不覆寫。

## 2026-09-28 TimesFM-3 personal research activation

- 使用者已明示用途為 personal / non-commercial / non-production research。官方/本機身份固定為 google/timesfm-3.0-pytorch、revision=43046b85ec22d584a13f8098c2ed39c889e129c2、timesfm==3.0.2；weight license=timesfm-non-commercial-license-v1.0，code license=Apache-2.0。TimesFM-3 不升格為 production/default-serving 必需模型。
- predict_timesfm 改為顯式 research gate：必須傳 PERSONAL_NONCOMMERCIAL_NONPRODUCTION_RESEARCH；缺少/錯誤 ack 在抓行情與載模型前即 RESEARCH_ONLY_BLOCKED。research singleton 即使已初始化，每次 access 仍重新驗證 ack。原 get_timesfm() 仍是 SERVING 並被阻擋；另設 get_timesfm_research()，兩者 singleton 分離。
- Gate 對 model-registry schema、research purpose、commercial/production flags、weight license、package exact version、pinned snapshot、revision、build fingerprint fail-closed。研究載入固定 local_files_only=true，不自動下載。future covariates=false；past-only covariates=true。
- Actual local verification：CUDA exact revision match PASS；univariate inference PASS；past-only covariate inference PASS；optional model suite=5 passed。實際 research predict_timesfm("^TWII", horizon="1d") PASS，輸出保留 TIMESFM3_NON_COMMERCIAL_ONLY 及 research usage metadata。Focused gate regression=46 passed / 44 warnings；cross-layer=107 passed / 2 deselected / 44 warnings；full offline（只排除既有 recorder owner-mutex）=2198 passed / 1 skipped / 24 deselected / 152 warnings，exit 0。
- 這只是 runtime/engineering enablement，不是新模型優勢證據；PREDICTIVE_GAIN=false、CALIBRATED=false、TRADING_EDGE=false。沒有 production service/default ensemble promotion、fine-tune、recorder/runtime/broker/account/order 動作或 JNU sealed evidence replay。source/config build=ed430c7fabbdd64b。

## 0.TW Taiwan-stock P0 correctness audit（2026-09-28）

- 這是 correctness / semantic / architecture 修復，不是新的模型挑選或精度證據。source/config build=`c0f52deac6ba33d8`。JNU P2/HPQ1/P5 證據邊界完全不變。
- 新共用資料契約：`TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1` + `FORWARD_EFFECTIVE_DATE_REFERENCE_RESET_V1`。Taiwan inference、classification backtest、TS validation 都走同一 corporate-action normalizer；future action 只從 effective date 向後生效，不回寫 prior features。必要 reference-reset channel 缺失、同日 factor 衝突、或無事件解釋的 >12% raw jump 都 fail closed。
- 事件來源使用 FinMind 免費 reference tables：`TaiwanStockDividendResult`、`TaiwanStockCapitalReductionReferencePrice`、`TaiwanStockSplitPrice`、`TaiwanStockParValueChange`；事件本身不進 predictive features。FinMind raw price 明標 `RESEARCH_PROXY`，只有 direct TWSE `STOCK_DAY` raw data 才標 `OFFICIAL_DAILY`。模型在 continuity basis 運算後，絕對價格輸出再映回 current raw basis。
- 真實 3706 audit：483 rows，2024-09-30..2026-09-24；2026-09-09 reference reset before=91.3 / reference=80.27 / announcement=2026-08-24T11:11:58。raw 91.3->81.8 的機械落差經 continuity 轉為 101.4444->103.3780。這只證明資料校正契約工作正常。
- Backtest 任務語義拆分：classification 指標與 numeric-return regression 指標分開；classification 的 MAE/RMSE/pinball=`null`。majority comparator 由每個 fold 的 train 決定，再在同一 OOS origins 計 accuracy / balanced accuracy / macro-F1；promotion 要三項都勝過 comparator，balanced accuracy 另須高於 uniform 1/3。train majority prevalence 只作描述，不再和 balanced accuracy 混比。
- Gross strategy diagnostics 使用 `position * realized_next_bar_return`，明標 `GROSS_REALIZED_RETURN_DIAGNOSTIC_NO_COSTS`、`transaction_costs_included=false`。因此 Sharpe / PF / DD 不是含成本 EDGE。舊 mixed-scale persisted evidence 不得取得 direction-vote 或 ensemble-weight promotion eligibility；PerformanceStore additive migration 並把 DB NULL/NaN 還原為 JSON-safe `None`。
- P0 checkpoint 的 Taiwan AnalysisPacket 與 JNU evidence 已隔離：Taiwan 不掛 `ACCURACY_V2_P5_FORWARD`、JPX/TMF、iTRADER 或 Osaka Phase2V-C economic conclusion；Taiwan economic status=`ECONOMIC_EDGE_NOT_EVALUATED`。當時刻意停在 `model_result_in_packet=false` / `SEPARATE_ANALYZER_NOT_YET_PACKET_INTEGRATED`；這個 integration pending 已由下方 P1 完成，evidence gates 不變。
- 3706 isolated backtest smoke 只驗工程路徑：n=160、accuracy=0.3875、balanced accuracy=0.360236、macro-F1=0.351233、`beats_majority_baseline=false`、`DEGRADED`、direction-vote eligible=false；不構成 predictive-gain evidence。
- 驗收：focused=`61 passed, 28 warnings`；build/integration=`49 passed, 2 deselected`；full offline（僅排除既有 recorder owner-mutex）=`2147 passed, 1 skipped, 24 deselected, 149 warnings`，exit 0。`PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false`；無 scheduler/recorder/runtime/broker/account/order/model-tuning 動作。
- P0 當時的下一包是 analyzer/model result 接入 AnalysisPacket；下方 P1 已完成。剩餘 bounded Taiwan work 是 target-specific freshness / fundamental / flow 版本化，並在任何新 predictive experiment 前對 PE/PBR/EPS/月營收/news coverage 做同 cutoff、同 source-semantics 對帳。
## 0.TW.1 Taiwan-stock P1 AnalysisPacket integration（2026-09-28）

- P1 is an engineering integration only. It does not add a new model, tune parameters, reuse frozen JNU outcomes or create predictive/calibration/economic evidence. Source/config build=`b67a7174dc0ba93a`.
- `AnalysisPacket` adds `target_model_analysis` as a target-family-governed model-result surface. Taiwan packet construction calls the existing `analyze_taiwan_stock()` once; both packet reference price and embedded model result derive from that one corporate-action-governed path. The old independent packet reference fallback (FinMind -> TWSE -> yfinance) is removed.
- Reference/model basis alignment is explicit: analyzer computes on continuity-adjusted history, restores absolute forecasts to `RAW_CURRENT_BASIS`, and exposes the current raw close as packet reference. Only TWSE raw is `OFFICIAL_DAILY`; FinMind raw is `RESEARCH_PROXY`. A corporate-action integrity failure produces `DATA_INTEGRITY_BLOCKED` and cannot fall back to a weaker/raw target reference.
- Packet embedding uses a whitelist/public-safe transform. It keeps same-target identity, dataset/adjustment/source semantics, calendar/origin, sanitized base/ensemble price forecast fields and authoritative direction eligibility. It drops raw class scores, raw direction research internals, internal exception strings and the corporate-action event ledger.
- Taiwan same-target model output can be displayed only with scope=`TAIWAN_STOCK_SAME_TARGET_RESEARCH_UNVALIDATED`. Formal validated direction remains gated; public probability remains unavailable; `validation_claims` are frozen false for `PREDICTIVE_GAIN`, `CALIBRATED`, `TRADING_EDGE`. Taiwan economic edge remains `ECONOMIC_EDGE_NOT_EVALUATED`.
- Data-integrity BLOCKED also closes packet `may_present_as_direct_forecast`, `may_present_research_stance` and `research_stance_allowed`; conditional WAIT/repair behavior remains available. No yfinance or other weaker target fallback is permitted after the integrity failure.
- Taiwan/JNU evidence isolation is unchanged: no `ACCURACY_V2_P5_FORWARD`, JPX/TMF, iTRADER or Osaka Phase2V-C evidence is imported into the Taiwan target family.
- Acceptance: focused packet/data/public contract=`83 passed, 8 warnings`; build/integration=`87 passed, 2 deselected`; full offline (only existing recorder owner-mutex excluded)=`2151 passed, 1 skipped, 24 deselected, 152 warnings`, exit 0.
- P1 當時的下一包是 target-specific freshness/fundamental/flow/news context；下方 P2 已完成這個 engineering/data-context step，但沒有開 predictive experiment。
## 0.TW.2 Taiwan-stock P2 target-context contract（2026-09-28）

- 契約升級為 `TAIWAN_STOCK_CONTEXT_V3` / `FINMIND_TWSE_RECEIPT_TARGET_CONTEXT_ASOF_V3`；freshness 維持 `TAIWAN_STOCK_CONTEXT_FRESHNESS_V2`，reconciliation 維持 `TAIWAN_STOCK_SOURCE_RECONCILIATION_V1`。新增官方 cross-check `TWSE_OPENAPI_RECEIPT_CROSSCHECK_V1` 與 immutable receipt `TAIWAN_CONTEXT_RECEIPT_V1` / `APPEND_ONLY_CONTENT_ADDRESSED_RECEIPT_TIME_V1`。Context role 仍為 `TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE`，`predictive_feature_allowed=false`。
- Receipt store 位於 canonical `MARKET_AI_DATA_ROOT/research_outputs/taiwan_context_receipts/snapshots` 且 gitignored。每筆 receipt 綁定 source context schema、symbol/stock_id、cutoff、實際 retrieved_at、payload hash；以 exclusive-create 寫入，不覆寫。完全相同 receipt 冪等，後續 revision 產生新 identity，tamper/hash mismatch fail-closed。Decision replay 只選 `retrieved_at <= decision_time` 的既存 receipt，因此 future revision 不得污染過去 decision。
- TWSE 官方 current-table 只作 receipt-time cross-check，不倒灌為歷史 PIT：`/exchangeReport/BWIBBU_ALL` -> valuation、`/opendata/t187ap05_L` -> monthly revenue、`/exchangeReport/MI_MARGN` -> margin/short、`/opendata/t187ap14_L` -> EPS report。Current free OpenAPI 未找到 target-level T86；`TWT96U` 是可借券賣出量而不是 lending transaction volume；現有 foreign-shareholding endpoint 只有類股/Top20 coverage，故都不拿來替代原 target channel。
- 3706 real receipt smoke：cutoff=`2026-09-27T19:35:21.385298Z`、retrieved_at=`2026-09-27T19:35:23.701581Z`，receipt=`tw-context:5e753d7b794eb675e78cf479cd2867e6`。因 receipt 晚於該 cutoff，`historical_backfill_eligible=false`；在後續 decision time 能成功選回同一 immutable receipt。這證明 future receipt replay 工程路徑，不證明歷史回填或預測能力。
- 實際官方 cross-check：TWSE 與 FinMind 在 2026-09-24 valuation 對上 PE=14.02、PBR=1.37、dividend_yield=5.1；2026-08 月營收 normalized=13,557,215,000 TWD、MoM≈0.05638 亦對上，TWSE 另有 YoY≈1.198933。TWSE MI_MARGN 現值與 FinMind 相符，但官方 current table 無日期欄，所以不做同日 reconciliation。TWSE EPS report=2.58，而 FinMind EPS context=1.48；report semantics / exact publication timestamp 未驗證等價，故雙方保留、不平均、不升級成 PIT feature。
- AnalysisPacket 現在輸出 receipt status/id/policy；capture 成功只表示 immutable receipt prerequisite 已完成，research gate 改為 `BLOCKED_UNTIL_PREREGISTERED_FEATURE_LABEL_SPLIT_PROTOCOL`，`predictive_experiment_data_ready=false` 仍固定。Live-built context 本身仍 `historical_revision_safe=false`；只有 decision 前已存在的 receipt 可標 receipt-time revision-safe。
- EPS 若要成為 historical feature 仍缺 verified exact publication timestamp/definition；target-specific news 仍 `NOT_AVAILABLE`，禁止 generic-web fallback 與 news-sentiment probability。
- Acceptance：focused=`69 passed`；build/integration=`131 passed, 2 deselected, 8 warnings`；full offline（只排除既有 recorder owner-mutex）=`2179 passed, 1 skipped, 24 deselected, 152 warnings`，exit 0。source/config build=`d5c355e8b0ea708f`。
- `PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false` 不變；沒有新增模型、調參、開 predictive experiment、重播 JNU evidence、scheduler/recorder/runtime/broker/account/order 動作。
- Forward receipt accumulation 已落成 tracked protocol `TWCTXFORWARD.1` / `taiwan_context_forward_receipts_v1`，protocol hash=`009e0f09b958b8a5ff88bdd3ced7b2f094532a131447fa59e2b8c7d4c5578691`。凍結 28 個 FinMind candidate factor 的 provider/dataset/units/observation-period/availability semantics；EPS、付費持股集中度、target-specific news 明確 blocked，config 不能靜默解封。
- 計數治理：retrieval identity=`receipt_id`；source version=`stock_id+factor_id+observation_period+provenance_hash`；independent observation=`stock_id+factor_id+observation_period`。同 period revision 只增加 version、不增加 independent observation；相同 source row 重抓只增加 retrieval。Replay effective available-at=`max(source available_at, receipt retrieved_at)`；future receipt 先依 decision time 排除，再做 contract 驗證，且 historical inventory 不暴露當時尚不可見的 future receipt ID/count，避免未來 malformed revision 或 metadata 反向污染過去。
- 第二次 real 3706 public-source capture=`tw-context:0ceee9d66bc73d607dabb06c82c46fe9`，cutoff=`2026-09-27T20:05:01.117562Z`、retrieved_at=`2026-09-27T20:05:04.491538Z`，`historical_backfill_eligible=false`。目前 inventory=2 receipts / 28 tracked factors / 27 factors 有 replayable observation；`monthly_revenue_yoy` 尚無 counted observation。代表 factor 仍是 retrieval=2、source_version=1、independent_observation=1、repeated_retrieval=1、revision=0，因此第二次重抓不是第二個獨立 forward sample。
- AnalysisPacket 已輸出 forward protocol id/hash/status、receipt count、tracked/observed count、blocked channels；receipt failure -> `BLOCKED_RECEIPT_CAPTURE_UNAVAILABLE`，candidate drift -> `BLOCKED_CANDIDATE_SEMANTICS_CONTRACT`，兩者健康仍只到 `BLOCKED_UNTIL_PREREGISTERED_FEATURE_LABEL_SPLIT_PROTOCOL`。`predictive_experiment_data_ready=false` 不變。
- Manual collector/inventory=`scripts/collect_taiwan_context_receipt.py`；沒有安裝 scheduler。Acceptance：focused=`44 passed`；cross-layer=`143 passed, 2 deselected, 8 warnings`；full offline（只排除既有 recorder owner-mutex）=`2191 passed, 1 skipped, 24 deselected, 152 warnings`，exit 0。source/config build=`f49d63255f3e0ac7`。
- 下一個 bounded Taiwan package：隨時間累積真正新的 observation periods 並檢查 revision，不把 re-fetch 灌成樣本。EPS/news 繼續 blocked；未來 predictive feature 仍須另行 preregister feature/label/split/purge/seed/trial-cap 與新未曝光 evaluation data。

## 0. P0/P1 實作快照（2026-09-27）

- 實際施工分支 `codex/vnext-audit-handoff`，本包進場 base HEAD=`fc6bd6830ecfed642c3c268e953ec3385eac08b8`；source/config worktree build=`a11cbb922621e730`。既有 `scripts/register_jpx_micro_sync_task.ps1`、`scripts/run-hidden.vbs` 保持未追蹤且未提交。
- P0：本機 x64 venv 是 Python 3.12.13、`chronos-forecasting==2.3.2`、`timesfm==3.0.2`。Chronos-2 registry revision=`29ec3766d36d6f73f0696f85560a422f50e8498c`，TimesFM-3.0=`43046b85ec22d584a13f8098c2ed39c889e129c2`；兩個 exact snapshot 都存在本機 cache。loader 現在都明確傳 registry revision，不再以「cache 第一個 snapshot」當 loaded revision。
- Chronos-2：官方/目前安裝 API 的 `Chronos2Pipeline.predict`/`predict_df` 支援 multivariate、past covariates 與 future covariates；P3-A 已讓本地 `ChronosAdapter.predict` 支援**有 PIT provenance 的 past-only covariates**，但 future covariates 於本包明確 fail-closed、multivariate 仍未實作。registry 分別記 `upstream_support.covariates=true`、`adapter_implemented.past_only_covariates=true`、`adapter_implemented.future_covariates=false`、`local_verified.covariates=false`。先前 `HF_HUB_OFFLINE=1` pinned CPU actual load 在120秒逾時，P3-A 不以 cache 或 fake pipeline 冒充 runtime weights 驗證。[R2]
- TimesFM-3.0：官方權重條款明確是 non-commercial / non-production。adapter 預設 purpose=`UNKNOWN` 並 fail-closed；研究 tournament/smoke 必須明示 `RESEARCH`；serving singleton 與 deep health 明示 `SERVING` 而被 gate 阻擋。shallow status 顯示 `RESEARCH_ONLY_AVAILABLE_NOT_LOADED`；權重未刪除，沒有啟動/切換 live service。[R3]
- P1 target contract 已落地：`decision_time`、`reference_price`/`reference_price_available_at`、`target_start`/`target_end`、`target_measure`、`exact_contract`、`forecast_horizon`、`label_available_at`。full-interval forecast 強制 `decision_time <= target_start < target_end`；reference 必須已可得；label 不得早於 target end。
- JNU 語義分離：`NEXT_OSE_SESSION_SETTLEMENT` 與 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION` 是不同 target。JPX Daily Report 官方說明約於**次營業日 09:00 JST**更新；假日交易統計會與假日前夜盤/後續營業日資料合併，不單獨發布，因此不得把 holiday-session outcome 假裝在前一日 15:45 已知。[R8]
- 一個跨市場切片已完成：沿用既有 FeatureStore/as-of provenance，固定 exact factor contract，產生 `factor_lagged_return = latest/prior - 1`。packet 保存 event/available/received/provider time、provider/source/frequency、venue/session、relation、contract、snapshot/lineage、age 與 source/value content hash。拒絕 future/late、非 PIT、安全狀態錯誤、stale、proxy relation mismatch、roll、series semantics/contract mismatch、duplicate time、non-finite、缺 bar gap、snapshot 缺失；future revision 不改過去 packet；labels 不進 features。
- P0/P1 初始包當時的只讀盤點確實是 NQ/ES/JY/TMF 無合格列，因此當時輸出 **ENGINEERING PASS / DATA_NOT_READY**；這是歷史 checkpoint。P3-B 後續已用官方 TAIFEX TMF exact-contract settlement 與實際 receipt-time provenance 建立 REAL DATA_READY packet；不得把新的資料狀態倒寫成 P0/P1 當時已 ready，也不得把它誤稱模型 market validation。
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

## 0.2 P3-A Chronos-2 past-only covariate 工程（2026-09-27）

- 實際進場 HEAD=`2df217af438e6d078cec768f969bab9eb4f0f4bb`、build=`f9e7b0ac3ce7ea69`；P3-A 完成後 source/config build=`2729cb4b2bcd1cb7`。只保留原本兩個未追蹤排程檔，沒有 live runtime handover、recorder restart、下單/帳戶動作或 fine-tune。
- 依本機 `chronos-forecasting==2.3.2` 實際 API 施工：`Chronos2Pipeline.predict` 接受 list-of-dict，其中 `target` 必填、`past_covariates` 是與 history 等長的 named 1-D arrays、`future_covariates` 是 prediction_length 等長的已知未來欄位。P3-A 直接走 dictionary API；不使用 `predict_df`，因後者要求 regular timestamps，不能為了 JPX/OSE 假日把不存在的日曆 bar 補成規則序列。
- 新 `ChronosPastCovariate` 強制逐筆 `values / event_time / available_at / source_hashes / feature_version`。adapter 在載權重前驗證：target/covariate 1-D且有限、長度一致、若都是 pandas Series 則 index 完全一致、event time strictly increasing、`event_time <= available_at <= decision_time`、source hash逐筆存在。任何 future-covariate argument（含空dict）一律 `FUTURE_COVARIATES_BLOCKED_P3A`；P3-A 不因上游支援而自動允許 future market covariates。
- Covariate identity hash 包含值(float32 content)、逐筆 event/available time、source hashes、feature version、decision time與 target index hash；`chronos_forecast.input_data_hash` 會和該 identity 合成，forecast config 也區分 plain vs past-only mode，避免同數值但來源/修訂/時間對齊不同時誤用舊cache。
- 新 P1→P3-A bridge 不排序、不future-fill、不混contract。只有全部 `engineering_status=PASS + data_status=DATA_READY + evidence_origin=REAL`、同 representation/factor contract/feature version/P1 protocol、packet decision/source event嚴格遞增、feature available不晚於packet decision且packet decision不晚於final decision時，才生成 Chronos covariate。synthetic packet 明確保持 `DATA_NOT_READY`；mixed identity、late/revised/future、reordered packet、duplicate/非單調 target index 都拒絕。
- 安裝版 preprocessing 的直接工程驗證 PASS：同樣的 `{target, past_covariates}` 送進 `Chronos2Dataset`，32點 target + 1 covariate 形成 context shape `(2,32)`；3-step future covariate slots 全為 NaN，證明沒有默默注入 future covariates。這只驗 installed API/schema，不等於實際權重 inference 或市場準確率；`local_verified.covariates` 維持 false。
- 真實資料只讀盤點仍為：`features.duckdb` 存在，NQ/ES/JY/TMF candidate groups=`0`。因此**沒有**執行真實 univariate-vs-covariate ablation，沒有 PREDICTIVE_GAIN、沒有 CALIBRATED、沒有 TRADING_EDGE；synthetic/fake pipeline 僅驗工程契約。
- 驗收：P3-A/P1/horizon focused=`33 passed`；加入bridge=`37 passed`；reproducibility/build integration=`47 passed`；full offline（只排除既有 recorder owner-mutex case）=`2047 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。installed Chronos schema validation exit 0。
- P3-B 已完成資料入口施工並取得第一個 REAL exact-contract receipt-time-causal packet；下一步改為累積**獨立 forward origins**，數量足夠後才另行預登記同-origin univariate vs past-only covariate ablation（固定 primary loss/delta/splits/trial cap/seed/coverage）。在 standalone covariate path 尚未證明因果增益前，不進 residual shrinkage、ensemble weight、regime 或 fine-tune。

## 0.3 P3-B 官方 TAIFEX exact-contract 資料就緒（2026-09-27）

- P3-B 進場 HEAD=`f8ecfdb069dbb558ed77ed3196aa6212e4c67f7f`；完成 source/config build=`a8fb56c5b7859e90`。沒有啟動/重登 recorder、沒有 broker 帳戶/部位/下單、沒有模型 fine-tune 或 market-performance certification。
- 先嘗試 CME 官方公開網站路徑，但本機收到 CME 明確 403：其網站 Data Terms 禁止 automated scraping；因此**沒有**做 header/cookie/browser 繞過，也沒有把被禁止的網站頁面當資料源。改用 repo 既有 TAIFEX 官方 provider，資料來源契約原已標 `OFFICIAL_DAILY / EXACT / 台灣期交所公開資料`。
- 修正 `TaifexProvider`：官方下載區間超過一個月在 network 前 fail-closed；HTML/error page 不再被 pandas 誤讀成資料；CSV schema 必須包含交易日/契約/到期月/close/settlement/session；官方 data row 比 header 多一個 trailing empty field 時只剝除尾端空欄，不允許任意欄位漂移；snapshot ID 以 query+content hash 產生，`received_at` 使用 cache/fetch 實際 receipt time。預設窗口縮成28天，避免舊40天預設違反官方一個月限制。
- 歷史 publication time 不可從交易日猜。TAIFEX historical CSV 沒有逐列發布時間，所以所有回補 row 的 `available_at` 一律是**本次實際收到時間**，不得回填成13:45/15:00或任何假定公告時間。這使它們只可供 receipt 之後的 origin 使用，不能拿來重寫過去 OOS。
- Materializer 只接受 `TMF + YYYYMM + 一般交易時段 + finite positive settlement`；exact contract=`TMFYYYYMM`、roll=`NONE`、series=`CONTRACT`、event time 使用既有 TAIFEX session truth（日盤13:45；到期日13:30）、source snapshot 必填，最後仍走既有 FeatureStore `DERIVED_DAILY` gate。calendar spreads (`YYYYMM/YYYYMM`) 不進資料；盤後 rows 不進 settlement feature；zero/missing settlement 明確忽略；同 event/contract 重跑同值 idempotent，不同值/duplicate 則 fail-closed conflict，不覆寫舊 PIT 值。
- 真實 snapshot=`taifex-daily:49c4bdbfd9b5affa6494f97a70c6f633`、receipt=`2026-09-27T09:41:01.678337Z`。首次 materialize：107 exact monthly rows 成功；官方 TMF202609 2026-09-16 `結算價=0` 一筆忽略；174 spread rows、275 after-hours rows 排除。修正後重跑為107 `ALREADY_MATERIALIZED`、0 blocked。資料庫/行情保持本機 data root，不提交git。
- JPX 公開 settlement provider 同步只讀取得 2026-09-25 Nikkei 225 Micro Futures；`202610` settlement 的實際 receipt=`2026-09-27T09:45:58.094649Z`。以固定 decision origin=`2026-09-27T09:46:00Z`、exact target=`JNU2610` 建 `NEXT_OSE_SESSION_SETTLEMENT` contract；TMF202610 P1 packet 為 `ENGINEERING PASS / DATA_READY`，feature available=`2026-09-27T09:41:01.678337Z`、source hash=`6129f45e37d7d784c8cca375`、cache identity=`9705080693fb9146c0d6ca0f`。這只證明 REAL/PIT data plumbing，不代表 PREDICTIVE_GAIN、CALIBRATED、TRADING_EDGE 或 clean historical OOS。
- P1 stale gate 修正：合法 daily previous-session `CLOSED_MARKET_REFERENCE` 不再被字串判定誤殺；真正 stale 仍由 `available_at` age、point-in-time、roll/contract/series/gate 等檢查拒絕。
- 驗收：P3-B focused=`38 passed`；integration（含factor routing/horizon/reproducibility/build freeze）=`86 passed`；full offline（只排除既有 recorder owner-mutex case）=`2054 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。真實 materialization idempotency PASS。
- P3-B 後不再空等 forward outcome。P4 已施工 no-new-forward robust analysis；真正 predictive promotion 仍等待獨立 forward receipt-time origins。Chronos univariate vs past-only covariate ablation 仍須在樣本量達預先固定門檻後，先 commit/push 專用 protocol，再比較同-origin，不能拿 P4 development 結果替代。

## 0.4 P4 無新前向 outcome 的穩健分析＋開源隔離合併（2026-09-27）

- **先凍結、後結果**：P4 protocol/OSS/future-data manifest 先於任何新 quantile/conformal outcome 提交並 push，prereg commit=`fb9e60a9885161986782d1a54dc79632b507e422`。當時 build=`ecac7c645590f16e`；engine 完成後 source/config build=`2e93ec6940904780`。P4 protocol hash=`646389ec5497c8935480848ee946a59fccebacf9ed330c9b4cbb19b20324f758`。
- P4 不推翻 P2：point champion 固定 `ZERO_RETURN_NAIVE / LAST_AVAILABLE_SETTLEMENT`；exposed quarantine 仍禁止 fit/selection/claim；final-forward 仍未開；post-development public history只能作 origin-causal feature context，不能用 post-development labels 重選模型。future fill、跨限月拼接、label-as-feature 繼續禁止。
- 無新 outcome 時仍可工作：EWMA daily-return volatility 固定 λ=0.94（描述風險，不選模）；波動 state 只用 development median 分 LOW/HIGH，不切換模型；strong direction 需要 predictive gain，否則 abstain；exact-contract 缺失或資料品質失敗則拒答。
- Conformal：zero-return baseline 一步報酬絕對殘差、development-only、minimum 20、buffer最多60；固定 50/75/90% coverage。chronological label-maturity prequential 結果（83 development origins、63 eligible）：static coverage 50/75/90=`0.50794/0.80952/0.92063`；90% interval mean return width≈`0.08197`。adaptive conformal 目標90%、γ=0.01、只在 outcome available 後更新，development coverage=`0.92063`、final alpha=`0.112`。這些是**區間診斷**，不是條件勝率或 W4 機率校準。[R4]
- LightGBM quantile challenger 固定 q10/q50/q90、3個 current fits、無 tuning、development-only fit，不能取代 point champion。另做固定-setting chronological OOF proper-score 診斷：5 folds／50 same-origin OOF／15 fits，p10-p90 empirical coverage=`0.68`、mean width return≈`0.04789`、crossing rate=`0`；pinball q10/q50/q90=`0.00428664/0.00879193/0.00514520`。因此它保留 `CHALLENGER_UNVALIDATED`，不因 current quantiles 看起來較窄就升級。[R9]
- 當前 JNU2610（只作本包功能驗證）latest official settlement=`66140`，current EWMA return vol≈`1.327%`、state=`LOW_VOLATILITY`；development-fit 90% empirical interval≈`63439–68841`。固定 quantile challenger current q10/q50/q90≈`65023/65788/67440`。主點位仍是 66140 的零報酬 baseline；strong_direction=false、calibrated_probability=false、not_trading_edge=true。engine 首次整包約713ms、3個 current quantile fits約36ms；同process且上游series/meta已存在時有content-addressed cache，不需重fit。
- `analyze_jnu_direct` 已合併 fallback：若 Chronos/TimesFM 全不可用但 exact-contract history合格，仍回 `OK` 的 baseline＋development interval＋volatility context，而不是整段 `DIRECT_MODELS_UNAVAILABLE`。模型 ensemble 仍保留 audit/research資訊，但沒有證據時不取代 P2 baseline。
- Future-data acquisition 已預施工：`future_data_acquisition.yaml` 明列 JPX settlement、JPX/OSE Daily Report、TAIFEX TMF official settlement 三條 active public collector；OSE Micro/TMF/CME authorized quote 只綁既有 single-owner recorder capability，不登入、不restart；CME public website settlement 明列 DISABLED，因本次實際收到禁止 automated scraping 的403，不能繞過。`collect_accuracy_v2_public_sources.py` dry-run與實跑都證明 broker=false、credentials=false、recorder_touched=false；實跑 JPX settlement/archive OK、TAIFEX 107 rows全 idempotent/0 blocked。
- 開源合併按原規畫採**隔離 adapter，不整套塞進主env**。Qlib官方 tag v0.9.7/commit=`da920b7`/MIT 已固定於 manifest；實際 v0.9.7 `pyproject.toml` 支援Python 3.8–3.12且 `mlflow` 未設 `<3.13` 上限，故舊文件的 mlflow<3.13 衝突敘述已過期；但Qlib仍alpha且依賴面廣，所以 core venv install=false、live=false。已把 83 個 P2 development origins 匯出為 content-hashed parquet+manifest，quarantine/final=0，`qlib_imported=false`、`qlib_executed=false`。NautilusTrader只先固定 P7 offline-parity boundary：stable 1.231.0/commit=`27a8e54`/LGPL-3.0；v2.0.0rc5 不選，live=false。所有 adapter artifact 寫 `data/lab/`，現已 gitignore。
- MCP/packet 已合併 future-data readiness 與 no-forward gates：`get_data_coverage` 顯示 active/blocked/prebuilt來源；AnalysisPacket research gates 明示 `NO_NEW_FORWARD_OUTCOME_ANALYSIS=BASELINE_INTERVAL_VOLATILITY_ALLOWED`、`STRONG_DIRECTION_WITHOUT_PREDICTIVE_GAIN=BLOCKED`，並加入新 exact-contract snapshot／forward outcome 到達的 reanalysis conditions。
- 驗收：P4 protocol/build-freeze=`10 passed`；P4 engine/JNU=`21 passed`；P3/P4/MCP/packet integration=`94 passed, 1 deselected, 11 warnings`；full offline（只排除既有 recorder owner-mutex case）=`2067 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。Qlib dataset export、public collector實跑均 exit 0。
## 0.5 P5 不可變前向發布監測（2026-09-27）

- **先凍結、後前向**：P5 protocol 先 commit/push 為 `ec6109dd2e71e3973727f6a2f79544ae67f62973`，protocol hash=`bf8ea909892c26b3ee2ed088c47ccb2f68a50fa0715073a13145c8ee2d95d863`；在此之前沒有任何 P5 真實 prediction。current source/config worktree build=`3227e61e6a713cef`。
- P5 target 固定為 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION`。origin 是 reference session 官方 publication+5分鐘，canonical lateness 最多15分鐘；第一個允許的 publication-origin date=`2026-09-28`。缺 observed receipt、future receipt、stale reference、遲到 origin、跨到期限月都拒絕，不允許 backdated sample。到 roll 邊界時只選能涵蓋下一 target session 的最近 exact contract。
- 不另造平行 ledger：沿用 append-only `PredictionAuditDB`。每個 canonical origin 先凍結 point=`ZERO_RETURN_NAIVE/LAST_AVAILABLE_SETTLEMENT`、P4 development 90% empirical interval（若可用）、固定 q10/q50/q90 LightGBM challenger（若 non-crossing）；之後官方 target settlement receipt 到達且 label mature 才對每個 artifact append 綁定 outcome。相同資料 idempotent；revision conflict 保留第一筆並 fail closed。
- Forward evaluation 預先固定 minimum 20 settled canonical origins。point 主指標是 MAE_RETURN；interval 報 empirical coverage/mean width/interval score；quantile 報 pinball q10/q50/q90、q10-q90 coverage、crossing rate與同-origin q50-vs-point。origin coverage<0.80、20-origin interval coverage<0.75、或10-origin point error>development baseline 1.5x 只會**降級**；永不自動升級模型、永不把 interval 當 probability。
- Collector cadence 已工程化但未啟用排程：public-source-only runner 每個 Taipei local date 最多2次；task-plan script固定 weekday 08:05/08:15、套用前檢查本機 Taipei timezone。這次只 dry-run，**沒有 Register-ScheduledTask**。`data/automation/` 僅存 local operational state且 gitignored；不碰 broker、credentials、recorder owner或 order path。
- 真實 2026-09-27 P5 cycle：JPX settlement/archive=`OK`；TAIFEX snapshot 新增6 exact monthly rows、另107筆 idempotent、0 blocked；broker=false、credentials=false、recorder_touched=false、order_action=false。reference session=2026-09-25、target session=2026-09-28，nominal origin=`2026-09-28T00:05:00Z`；因執行時尚未到 origin，precommit=`WAITING_FOR_ORIGIN`，P5 prediction count 前後皆0。這是 operational/data evidence，不是 predictive gain。
- MCP `get_data_coverage`、`get_forward_test_status` 與 AnalysisPacket research gates 已暴露 P5 expected origins、canonical coverage、settled count、interval/quantile diagnostics與 downgrade state；讀取路徑在 audit DB 不存在時不會建立 DB，forward point 樣本不足10筆時也不重算 development drift baseline。
- 驗收：P5 focused=`16 passed`；integration=`111 passed, 1 deselected, 11 warnings`；full offline（只排除既有 recorder owner-mutex case）=`2083 passed, 1 skipped, 24 deselected, 132 warnings`，exit 0。P4 development conformal/quantile 成績仍不是 P5 forward 證據；下一步只能從 2026-09-28 起自然累積新 canonical origins，不能補寫錯過的 prediction。

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
- `ChronosAdapter.predict` 現已保留原單序列路徑並新增 P3-A past-only covariate dictionary 路徑；registry 的 `adapter_implemented.past_only_covariates=true`、`future_covariates=false`、`local_verified.covariates=false` 分開描述工程能力與重型 runtime 驗證狀態。官方 Chronos-2 支援 multivariate/covariates，但本地 multivariate/future market covariates 仍未開放。[R2]
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

## 8.1 P7 完工與系統 readiness checkpoint（2026-09-27）

P7 不等待市場 outcome 才施工，因為它驗的是獨立執行／成本 proxy／paper simulation／搬移重建，而不是預測效果。P7 protocol 已在任何正式 parity 結果前以 commit `3bd723e820b67212673c2ea5d7d83254fd7a11ae` push；protocol hash=`bc16ff60e8f9f113d94ce0c400464c32fa1200daaba4b2f0041a9ef4b0af6eb6`。固定使用 NautilusTrader 1.231.0 / commit `27a8e54` / LGPL-3.0、isolated subprocess/file contract、禁止 core venv install、live execution、serving dependency與 prerelease。

實機隔離環境位於 gitignored `data/lab/nautilus_trader_1_231_0/.venv`，實際 import/version=`1.231.0`。固定 synthetic normalized-bar parity 以64 bars、seed=20260927、兩次重跑驗證；正式結果兩次 digest 相同=`4b78da7e33b0da481260454a6f85d02542a82222318257a9508965de41e1b1ed`，64/64 bars、2 fills、1 closed position、0 open position，finite simulated account，no network market data / no live adapter / no external order action 全部 PASS。這只證明離線執行決定性與基本 order/fill accounting，不是 JNU 預測表現。

成本診斷沿用既有 `CostModel` 假設，不另造實盤成本：ZERO_COST=0 bps、BASE_COST=26 bps、STRESS_COST=120 bps round trip；只做敏感度/可靠性欄位，不聲稱實際成交成本或 economic edge。P7 simulated-paper acceptance 與 migration acceptance PASS；搬移 recipe 要求重建 `.venv`、設定/preserve `MARKET_AI_DATA_ROOT`、用 `scripts/provision_accuracy_v2_p7_engine.py --apply` 重建隔離引擎、另行重建 SDK/WinCred/task，不把 venv/密鑰整包複製到 Git，也不授權 runtime handover/recorder restart。

新增 `scripts/validate_accuracy_v2_system.py` 作整體 preflight。2026-09-27 實跑回 `READY_FOR_ANALYSIS_AND_GOVERNED_PREDICTION`：JNU direct model 真正載入成功，P4 no-new-forward baseline path=OK，P5=`WAITING_FOR_ORIGIN` for 2026-09-28T00:05Z，P7=`P7_ENGINEERING_PASS`。目前 point governance 仍是 settlement 66,140 的 zero-return baseline，development-fit 90% interval≈63,439–68,841；`PREDICTIVE_GAIN=false`、`CALIBRATED=false`、`TRADING_EDGE=false`、strong direction=false。P6 仍是條件式：沒有證明盤中OFI／共享訓練／新聞／fine-tune 的資料、runtime與獨立增益前，不為了「完工」強做。

P7 focused/contract + open-source protocol=`18 passed`；P7/P5/P4 affected-scope integration=`92 passed, 1 deselected, 11 warnings`。之後針對全系統進行新的完整驗證並修復三個語義一致性缺口：舊 Phase2 freeze 不再覆蓋 current Accuracy v2 truth、AnalysisPacket 不再誤稱沒有 JNU direct path、direct JNU horizon 統一成 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION` 並固定 2026-09-18 → 2026-09-24 假日回歸。最終 full-offline=`2112 passed, 1 skipped, 24 deselected, 143 warnings`，exit 0；MCP stdio=24 tools、Chronos實機CPU/CUDA/quantile PASS、TimesFM RESEARCH univariate/multivariate/past-only covariates/CUDA PASS、public collector PASS。完整矩陣見 `SYSTEM_VALIDATION_20260927.md`。

## 8.2 Data Continuity / Capability / Golden Answer checkpoint（2026-09-27）

為處理「未來 exact JNU 資料暫時或長期拿不到」而不製造假 target，本系統新增 `AV2.CONTINUITY.1`。它先讀 exact-contract official history，再比較 JPX/OSE Daily Report 與 receipt-timestamped settlement channel；量化 source channel count、matching channel count、hash、revision conflict 與 independent publisher count。兩個 JPX channel 仍屬同一 publisher，因此即使雙通道一致，也不能宣稱兩個獨立出版者。current actual state=`NORMAL_TARGET_DATA`；JNU2610 latest=2026-09-25 / 66,140；next published observation=2026-09-28；expected publication=2026-09-29T00:00:00Z；grace 後 stale threshold=00:30Z。實際最新 redundancy=`SINGLE_CHANNEL_ONLY`，context-confidence=`MEDIUM` 且 `context_confidence_not_probability=true`。

若 exact target reference 缺失、next expected observation overdue 或兩個 official channel 發生 value conflict，系統切到 `DATA_CONTINUITY_MODE`。此模式只允許最後可信 JNU settlement、P4 volatility/regime/empirical interval、官方事件與其他市場資料作 context/risk assessment；proxy 永遠不能代替 JNU target，不能新增 predictive-gain evidence、不能公開 calibrated probability、不能宣稱 trading edge。`analyze_jnu` 在 continuity mode 不呼叫 direct target model；P5 仍可 settle 已經在 origin 前凍結的 pending outcomes，但禁止新的 precommit。資料恢復後才回 normal target path；錯過的 prediction 不補寫。

新增 `AV2.CAPABILITIES.1` machine-readable registry，MCP 提供 `get_capability_registry` 與 `get_data_continuity_status`。每項 capability 固定回 `available / data_ready / evidence_level / user_visible / blocked_reason / details`，讓 Agent 不需從零散文字猜測可用性。實際 registry 共15項，current available=11、data_ready=11、blocked=8；predictive gain / calibrated probability / trading edge / live trading 仍 false。MCP stdio tool count 因此由22增為24。

新增 Golden Answer regression：禁止 direct target 退回 next-session wording、禁止 interval 被當 probability、禁止 legacy Phase2 VAR evidence 回到 current truth、禁止再說沒有 Direct Micro path、禁止 proxy=target、禁止未證明的 predictive/trading edge。P4 target 欄位也同步為 `next_published_observation_date`。

P5 natural-forward 準備再加一層 continuity guard，但 scheduler 仍未 apply。`run_accuracy_v2_p5_forward_cycle.py --dry-run` 實跑 `writes_prediction=false`；current preview 仍 `WAITING_FOR_ORIGIN` for 2026-09-28T00:05Z。continuity/capability focused=`43 passed`，affected integration=`95 passed, 1 deselected, 22 warnings`；第一次 full suite 只因舊 `tool_count_is_22` freeze 失敗，其餘2111 passed；修正介面 freeze 後最終 full offline=`2112 passed, 1 skipped, 24 deselected, 143 warnings`，exit 0。這些都是工程／語義／資料中斷韌性證據，不新增市場效果宣稱。

## 8.3 Settlement Forecast / Trading Path / Advisory closeout（2026-09-27）

工程判斷為 `PARTIAL_FIX`。Accuracy v2 Settlement Forecast 本身沒有 bug：其 target 繼續是 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION`。產品缺口在於使用者詢問開盤路徑、日夜盤、Touch/Break/Acceptance 時，不能把 official settlement forecast 當成 execution/session state。新增 contract `docs/architecture/jnu-settlement-trading-path-advisory-contract.md`，硬分 `SETTLEMENT_FORECAST` 與 `TRADING_PATH_DECISION_SUPPORT`。

Trading Path 只讀 Yuanta quote-only durable archive 中 market 207 的 true JNU Micro quote identity。FunctionList 目前解析 decision contract=`JNU2612`，night quote=`JNUPM2612`；official settlement target 則為 `JNU2610` / 66,140。不同 contract month 時 `CONTRACT_MISMATCH`，禁止 settlement-to-session gap/basis arithmetic。實際 archive 9/25 的 verified day close boundary print=66,290（15:45:01 JST），但 day coverage 因第一筆 price observation 僅到08:59:34 JST、沒有 opening-boundary observation 而保持 incomplete；night data 只到22:11:52 JST、last=66,320，沒有 06:00 boundary，因此 `TARGET_PREVIOUS_NIGHT_CLOSE=null`。外部 review 提供的66,475不被 repo 證據支持，未寫入系統。

`analyze_jnu_trading_path` 新增 descriptive Trend/Box/Mixed、Price Activity Profile 與 explicit-level Acceptance。最新真實 night session 僅取同一 session、不跨日混合：66,190–66,590、last 66,320、42個5m observed-price bars、state=MIXED；level=66,600 的 smoke 為 touch=false/break=false/acceptance=false。這些 bar 是 quote snapshot 聚合，不冒充 exchange OHLC。Price Activity Profile 是觀測頻率，不是成交量；目前 durable archive 沒有可證明的 `TRADE_TICK + DealPrice + DealVol` schema，因此 Volume Profile fail-closed=`VOLUME_PROFILE_NOT_AVAILABLE`，Watchlist Vol 不接受為成交量。支撐壓力仍不自動生成。

Direct settlement model 新增 contributor provenance：0 model=`BASELINE_ONLY`、1 model=`SINGLE_MODEL_DEGRADED`、2+ model=`MULTI_MODEL_AVAILABLE_ENSEMBLE`。實際 runtime 為 Chronos-2 available、TimesFM-3.0 `ModelUsageBlocked`，因此現在是 single-model degraded；不能描述成多模型一致。此修正不改 point champion、P2/P5 evidence 或任何 promotion gate。

News/event 只接既有 official provider/calendar framework 作 context/risk/abstention；本機目前沒有 materialized `data/events/events.duckdb`，所以 dated-event data_ready=false，Trading Path 明示 `PROVIDER_FRAMEWORK_ONLY_NO_DATED_EVENTS`。`LIVE_NEWS_FUSION_DEFERRED_P6`；未加入 unrestricted weekend-news ingestion、LLM sentiment probability、FinGPT/news fine-tune 或 OFI。

新增 `get_itrader_advisory` 純文字翻譯層。策略模板 GENERAL/OCO/TRAILING；只有使用者本次明確給 side+quantity+條件才產生個人化欄位，多單平倉=SELL、空單平倉=BUY。JNU reference 5 points/tick、JPY10/point、JPY50/tick/contract。UI mapping=`PARTIALLY_VERIFIED_PUBLIC_YUANTA_CONDITION_ORDER_CONCEPTS`；永遠 NO ORDER / NO TRADING / NO ACCOUNT ACCESS / NO POSITION QUERY / NO BROKER LOGIN / NO BROKER MUTATION。

MCP由24增至26 tools；Capability Registry由15增至18 capabilities（actual available=14、data_ready=13、blocked=10）。Agent compact/full prompt與快捷提示已加入 Settlement-vs-Trading-Path routing、single-model degraded、Acceptance、Volume Profile fail-closed與 broker UI text boundary。功能驗證：final focused=52 passed, 22 warnings；affected integration=121 passed, 2 deselected, 22 warnings；full offline=2127 passed, 1 skipped, 24 deselected, 143 warnings, exit 0。build=`d16fb05386cdc8ea`。以上不新增 predictive gain/calibration/trading-edge 宣稱。

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
- **R12** [Qlib v0.9.7 release](https://github.com/microsoft/qlib/releases/tag/v0.9.7)、[v0.9.7 pyproject](https://raw.githubusercontent.com/microsoft/qlib/v0.9.7/pyproject.toml)：本包固定 v0.9.7=`da920b7`、MIT、Python 3.8–3.12；此 tag 的 `mlflow` 依賴未設 `<3.13` 上限。仍用隔離 subprocess/file contract，不把Qlib框架變成PIT/audit主腦。
- **R13** [NautilusTrader releases](https://github.com/nautechsystems/nautilus_trader/releases)：P7預留 stable 1.231.0=`27a8e54`、LGPL-3.0；目前2.0為release-candidate線，不以pre-release直接接live capital。LEAN仍保留為P7另一候選，P7只擇一做offline parity。

## 10. ChatGPT施工與跨對話規範

WebCodex主施工，Remote Desktop Commander只作失效備援；本機Codex可直接檔案/Git/測試。每次以當前工具schema發現功能，先runtime_status/work_on_project定位，不沿用舊session ID。先核對repo/HEAD/dirty/build，再讀AGENTS與本文件；只回傳bounded diff/log tail。備援前查舊job避免雙writer。finish snapshot是輔助，不代替exit code／測試／push／CI。

保持quote-only，不登入或重啟既有recorder、不下單／查帳戶部位／拷貝密鑰，不改其他專案。已授權工作包內自行修正常規問題；使用者中途補充不代表取消任務。未完成／資料不足／尚未驗證清楚分開。每包更新repo交接與來源快照、提交推送程式文件，不上傳私有行情／DB／模型權重。PR不自動merge；遠端不可用才提供可回貼備援prompt，不能假裝已施工。

若需OpenCode回貼，只在兩遠端工具不可用時採用；先查官方 https://opencode.ai/docs/ 與實際模型列表。使用者曾稱的DeepSeek版本/high/max不是已驗證API名稱，不杜撰設定參數。
