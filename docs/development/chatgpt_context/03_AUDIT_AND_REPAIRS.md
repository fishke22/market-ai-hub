# MARKET_AI_HUB 查核與實修報告

查核開始：2026-09-24；最終交接：2026-09-25（Asia/Taipei）。應使用本報告的修補後狀態，不再把初版稽核反例當成現況。

修補 commit：40fd77aeb35532e1b4dde42128f214b1c4683b1b（最終程式/安裝/測試基準；後續純文件 commit 見 PR）；PR：https://github.com/fishke22/market-ai-hub/pull/55（OPEN，尚未合併 main）；CI：PASS：1679 passed、15 skipped、34 deselected、110 warnings，48.76s；https://github.com/fishke22/market-ai-hub/actions/runs/36025129753；對應實作 commit 40fd77a；remote：codex/quote-hub-correctness 已推送並核對實作 SHA；main 基準仍為 eb9202a。

## 基準與查核範圍

最初查核基準 d649059（PR #53），當時新 recorder 未提交。本輪施工期間，另一棒將原功能以 PR #54 合併為 eb9202a157ce8831fdf6442a0f9faa5b84387d92。本輪修補以其為父基準，保留既有功能，沒有 reset/clean/stash。實際 repo 為 D:\MARKET_AI_HUB，交接包工作區不是該產品 repo。

已盤點 650 個當時受版控/未忽略文字檔，讀 bytes、UTF-8、hash 與 Python AST；重點語義查核涵蓋 architecture、V2-H/I、PPM gate、public whitelist、packet、安裝/CI/路徑與完整新 recorder。這不是對所有私有行情、SDK、權重或所有程式路徑的完整認證。

## 已修正（程式與離線測試）

| 編號 | 原因 | 根因修補 | 驗證邊界 |
|---|---|---|---|
| H1 | clear buffer 後寫檔且吞例外 | QuoteBuffer lock/有界 queue；writer 成功後才 ack；失敗保留批次；Parquet partial → atomic replace；pending/drop/error 可見 | 寫失敗與寫中 callback replay 通過；不承諾斷電零丟失 |
| H2 | 新 bid callback 刷新舊 trade 的整筆時間 | 各欄 field_provenance；top received_at 僅指 callback；清除不相干 source_time | trade→bid 反例通過；後續 reader 必須使用欄位時間 |
| H3 | CLASS_SCORE + CALIBRATED 字串可放行 | audit helper 在無 fitted evidence resolver 的 2I.1 一律 fail-closed；保留獨立 PPM typed gate | NaN/Inf/越界/任意 evidence ID 都拒絕；未聲稱之前 public MCP 可利用 |
| H4 | Python/PowerShell 資料根不同、只有 PID 判互斥 | 三腳本共用 recorder_root；相對 DATA_ROOT 固定相對專案根；Windows lifetime named mutex | 離線雙鎖競爭/釋放與 relocation 通過；舊無鎖程序靠 fresh heartbeat 防重入 |
| H5 部分 | 動態要求未驗 action/cap、無界 diagnostics | subscribe whitelist、路徑限制、4096-byte cap、最多10 requests/loop、200單批/5次每秒、200 dynamic/2000 total、atomic inbox、result、bounded callbacks | action/cap/path 反例通過；送出≠live，尚未實機驗速率/長期負載 |
| M3 | native 命令失敗仍可能報安裝成功 | 每步 LASTEXITCODE guard | PowerShell mock nonzero 確認整體失敗 |
| M4 | CI 覆寫 marker、SDK/連網測試誤進離線集 | 排除 optional/private/broker，vendor resolver 標 broker_diagnostic，兩個真下載測試標 live | 保留原測試/斷言；沒有以關 TLS 換通過 |
| M5/M6 | count≥2 稱 EVALUATED，readiness 可建表 | READY_FOR_EVALUATION + candidate-only scope；read_only DuckDB、不 migration，schema 問題 BLOCKED | 舊 DB bytes/schema 不變；評估 engine enum 仍2I.1 |
| M1/M2/M9 | 狀態、模型可用、授權/官方資料時間描述矛盾 | 更新 handoff/status/contracts/model/data 文件，歷史 STOP 標明已被新授權取代 | 公開 model card 核對；未因此啟用 challenger |
| M11 | build_id 漏掉新 runtime config | config 下 YAML/YML/JSON 全納入 fingerprint，LF normalization | 新設定內容改變 ID；CRLF/LF 同 ID；更新三個既有快照 |
| M12 | GitHub 乾淨 CI 缺 openpyxl，無法收集 Excel 解析測試 | requirements-runtime 與 pyproject 補列既有依賴3.1.5；未在本機另裝套件 | 本機 Excel/硬化回歸30 passed、4 deselected，exit0；Linux CI另列狀態 |
| M13 | constructor 強制載入 neuralforecast；mock WinCred 仍依賴真 Windows 模組；MLflow 整合混入輕量集 | 模型改 lazy import，缺件回 unavailable warning；完整 fake win32cred；MLflow integration 分類，sanitize 留 unit；宣告 research extra | 缺依賴及成功 dispatch/參數皆有離線回歸；未刪安全斷言、未安裝選配套件 |

## 實際測試

- 修補前相關既有測試：88 passed，exit 0；同時三項漏洞反例成立。
- 第一輪修補聚焦：111 passed、1 deselected，exit 0。
- 初次全套：1700 passed、3 failed、21 deselected；三個失敗都是舊 build snapshot，已依最後 source/config 指紋更新，未刪斷言。
- 最終驗證：1705 passed、23 deselected、132 warnings，165.76s，exit 0；預設 profile（不含 live/optional_model/private_data/broker_diagnostic）。
- 版本指紋：`192cdccf6173305e`；docs/tests 變更不改此值。
- 原始碼從 D 槽複製至 C 槽中文/空白路徑、非 repo cwd、相對 external DATA_ROOT：SOURCE_RELOCATION_SMOKE_PASS；沿用既有 interpreter/dependencies，**不是新 venv/乾淨 Windows/券商移機驗收**。
- 9 份 primary docs 相對連結檢查通過；外部連結不是逐 endpoint 實測。
- 秘密掃描已執行；六筆命中是基準版既有 getpass 提示文字（含一筆歷史報告範例），逐筆核對未變更。本次修改/新增內容零命中，沒有把原始命中值貼到對話。
- Codex 直接 shell 的外部 TWSE/Yahoo 驗證遇 TLS certificate chain 問題，未降低 TLS；live profile 與離線 profile 分開，不宣稱外網問題已修好。

關鍵測試：`tests/test_quote_hub_hardening.py`，以及原 V2-H2/I、Phase3A23、Yuanta contract。命令採 python -B -m pytest，獨立 MARKET_AI_DATA_ROOT / basetemp、禁 pytest cache；正式結果以 PR/本報告記錄為準。

## 2026-09-25 W2 field-aware reader/replay 後續

- 實作 commit：`825c19e7c67922eb7779d768ccd8b4207aae98cf`；runtime build_id `52837b5fc6444e3f`。
- 新 `quote_reader.py` 以既有 `yuanta_live_recorder.yaml` subscription identity + V2-A.2 factor/session registry 為唯一 routing truth；trade/bid/ask 各讀自己的 `field_provenance`，`source_time_of_day` 沒日期時不組成 exchange timestamp。
- 新 schema 缺該欄 `received_at` 會 typed reject；整個舊 schema 缺 `field_provenance` 時只降級為 `LEGACY_TOP_LEVEL_RECEIPT_ONLY`，不宣稱欄位 fresh。SPARK PM/day code 與 V2 session 不一致、錯 market/contract、unknown/unsupported representation、亂序、partial、write failure/overflow 皆有最小反例。
- V2-H lineage 會保留 reader 的 source snapshot ID、quality、contract identity；CLASS_SCORE/public probability gate 未變。
- read-only runtime inspection：目前執行中的 status 仍只有舊欄位，`latest.json` 22/22 都沒有 per-field provenance，因此明確為 `RUNTIME_ADOPTION_PENDING`。沒有登入/登出/訂閱/重啟。
- read-only 舊 Parquet 實測：最近檔 934 rows，其中 OSE 76 rows；5 筆有效 trade 可轉成 V2-A.2 且全部降級為 legacy receipt-only/delayed reference，71 筆沒有有效正成交價而拒用。只記 aggregate evidence，不提交私有行情值。
- focused regression：153 passed、1 deselected；final default suite：1717 passed、23 deselected、132 warnings，135.55s，exit 0。

## 2026-09-25 W2 Feature Store / packet provenance 後續

- 實作 commit：`5fe8906bd1237f7f89cd96dbbfa9383b8763281f`；runtime build_id `f09ff80765f94687`。
- Feature Store schema v2 以 non-destructive migration 保留既有 Phase-2C rows，另存 immutable V2-A.2 factor observations；只有 V2-A.2 live-eligible、dated、fresh、point-in-time safe 且 contract/roll 合法的 observation 才 materialize `v2a2-quote-1` feature。舊 schema/缺 event time/stale 仍可保存 provenance，但不能進 live model feature。
- 同一 observation replay 對 snapshot 與 feature 都 idempotent；lineage/value 衝突 fail closed。packet 的 read-only query 不會在缺 DB 時偷偷建立或 migration。
- Data Lake、Feature Store default runtime root 已統一到 `MARKET_AI_DATA_ROOT`；舊 `MARKET_AI_HUB_DATA_ROOT` 只保留 migration fallback，相關現役測試已改 canonical env。
- Analysis Packet 新增 bounded provenance summary，保留 source snapshot IDs/quality/contract/freshness，但不覆寫既有 reference price，也沒有新增 probability/trading 欄位。
- regression：155 passed/1 deselected；broader 265 passed/2 deselected；default 1726 passed/23 deselected/132 warnings，150.34s，exit 0；changed-file secret scan 0 hits；diff check PASS。

## 2026-09-25 W2 model-input contract closure

- 實作 commit：`9a11ce309ef5159545cb64e4ed8fa81ca0bbacfd`；runtime build_id `bed003b51f6d1f8b`。
- 新 model-input layer 以 read-only query 消費 Feature Store gated rows，固定 cutoff、representation、contract、frequency 與 lineage；later-available row 排除、mixed contracts/frequency、duplicate event time、history 不足均 typed abstain。
- public packet 只顯示 readiness metadata，不暴露輸入值；現有 broker source frequency=`TICK`，current model frequency=`1d`，因此 Osaka readiness=`INCOMPATIBLE_FREQUENCY`。禁止 silent resample / fake daily bar。
- W2 offline engineering path 標 `W2_OFFLINE_CONTRACT_PASS`，但 live recorder adoption、bar aggregation、DATA READY 仍未成立。
- regression：117 passed/1 deselected；76 passed/1 deselected；146 passed；default 1735 passed/23 deselected/132 warnings，141.75s，exit 0。

## 2026-09-25 W3.1 outcome / evaluation governance

- 實作 commit：`95289de6722c1477c5183e172384a3fd196050fd`；runtime build_id `98fe354dcc4fb275`。
- Prediction Audit 升為 2H.3；`sample_origin`、`label_window_id/start/end` 可在 prediction time 綁入 identity。有 sealed window 時，outcome 未到 `label_window_end` 或 `target_period` 不符會直接拒絕。
- 新 W3.1 governance 要求 timezone-aware `evaluation_as_of`，以及 target/instrument/horizon/model/model-version/artifact/label/sample-origin/event 的 homogeneous scope。`FORWARD_PRECOMMITTED` 與 `RETROSPECTIVE_REPLAY` 不混用，duplicate logical sample / superseded selection fail closed。
- W3.1 通過後才呼叫既有 2I.1 metrics；沒有改 Brier/log-loss/reliability 等公式，也沒有 calibration fitting。readiness 保持 `CALIBRATED=false`。
- audit DB default path 改走 canonical `MARKET_AI_DATA_ROOT`；相同 artifact identity 跨 prediction 綁定改為 typed reject，不讓 raw DuckDB constraint 冒出。
- 驗證：focused 85 passed；broader 236 passed/1 deselected；audit path/build 74 passed；final default 1749 passed/23 deselected/132 warnings，172.00s，exit 0；changed implementation/test secret scan 0 hits；diff check PASS。
- 上述 W3 測試使用 synthetic temporary DB，只算 ENGINE/GOVERNANCE PASS；真實 forward predictive evidence 仍未建立。

## 尚未完成，不能誤報已修好

1. **執行中的舊 recorder 尚未由本輪停止或重啟。** 新保護是 disk source / offline verified，不是 live deployment。不要讓新 agent 同時登入。先確認舊 PID、最後持久化批次与無重複 owner，再安排可回復交接；無法證明舊 RAM 全寫出時不能承諾無縫零丟失。
2. 自動 reconnect、授權拒絕後生命週期、session/contract 自動 roll、durable spool/WAL 尚未實作。新 status 保守標 NOT_CONTINUOUSLY_VERIFIED、MANUAL_SINGLE_OWNER、BUFFERED_NOT_ZERO_LOSS；跨 UTC 日提示 CONTRACT_REVALIDATION_REQUIRED。這些是下一工作包，不能把 flags 當已實現。
3. recorder→V2-A.2→V2-H→Feature Store→packet→model-input boundary 已完成離線契約；但 broker TICK 仍不相容現有 1d models，沒有 validated bar aggregation，所以 DATA READY / broker-driven inference 仍不成立。舊錄製資料無 per-field provenance，只能 legacy receipt-only 降級；新的欄位 received_at 仍只表示「此 callback 觀測到欄位」時間，不保證是成交發生時間。
4. Outcome horizon maturity / evaluation_as_of / homogeneous model-version-event scope 的 W3.1 工程契約已補足；**但真實 precommitted forward predictions/outcomes 尚未自然累積成證據**。2I.1 描述性 metrics 不可當 production calibration；維持 fitting NOT STARTED。
5. 真實 OOS / forward / 校準與淨經濟優勢仍無本次新證據。ENGINE PASS ≠ CALIBRATED ≠ EDGE。
6. 新 Windows、重建 venv、WinCred/COM/合法 SDK/模型權重重新配置與恢復演練仍需 W7；不能整包複製就保證即用。

## 回復與下一棒

本輪保留原檔備份於交接工作區 repair_backup；正式回復依 Git 父基準 eb9202a 與修補 diff 逐項 review，不 reset 使用者其他變更。未改 DB schema、未登入/登出券商、未下單/查帳務、未下載模型、未啟用 AUTO_TRAIN。

選配研究依賴已在 pyproject 的 research extra 宣告（neuralforecast 3.2.2、mlflow 3.16.1，取自本機既有版本）。需要這些研究功能時，在已重建 venv 使用 `python -m pip install -e ".[research]"`；核心安裝不強制載入它們。啟用前仍需驗證依賴/硬體/授權，不因安裝 extra 就自動訓練。

下一棒先核對最新 HEAD/dirty/PR 與實際 runtime。W2 離線契約與 W3.1 governance engine 已關閉；下一個無需 broker 維護窗口的工作是把最小 `FORWARD_PRECOMMITTED` prediction/outcome cycle 接到 2H.3/W3.1，開始累積真實可稽核樣本。若使用者另提供維護窗口，可先受控交接舊 recorder。W4 calibration fitting 只能在真實成熟樣本足夠後啟動。長期 Price/Probability Map 設計見 02_ROADMAP.md。
