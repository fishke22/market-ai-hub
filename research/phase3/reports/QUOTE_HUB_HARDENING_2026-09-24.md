# MARKET_AI_HUB 查核與實修報告

日期：2026-09-24；本轮應使用本報告的修補後狀態，不再把初版稽核反例當成現況。

修補 commit：3ea367ab4d5f5cd224857d6a8c8c04dc64f550d2（實作與測試基準）；PR：https://github.com/fishke22/market-ai-hub/pull/55（OPEN，尚未合併 main）；CI：GitHub lightweight CI 發布時執行中；以 PR checks 為準，未宣稱通過；remote：codex/quote-hub-correctness 已推送並核對 SHA；main 基準仍為 eb9202a。

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

## 實際測試

- 修補前相關既有測試：88 passed，exit 0；同時三項漏洞反例成立。
- 第一輪修補聚焦：111 passed、1 deselected，exit 0。
- 初次全套：1700 passed、3 failed、21 deselected；三個失敗都是舊 build snapshot，已依最後 source/config 指紋更新，未刪斷言。
- 最終驗證：1702 passed、23 deselected、132 warnings，175.88s，exit 0；預設 profile（不含 live/optional_model/private_data/broker_diagnostic）。
- 版本指紋：`7c3ea8b62785600a`；docs/tests 變更不改此值。
- 原始碼從 D 槽複製至 C 槽中文/空白路徑、非 repo cwd、相對 external DATA_ROOT：SOURCE_RELOCATION_SMOKE_PASS；沿用既有 interpreter/dependencies，**不是新 venv/乾淨 Windows/券商移機驗收**。
- 9 份 primary docs 相對連結檢查通過；外部連結不是逐 endpoint 實測。
- Codex 直接 shell 的外部 TWSE/Yahoo 驗證遇 TLS certificate chain 問題，未降低 TLS；live profile 與離線 profile 分開，不宣稱外網問題已修好。

關鍵測試：`tests/test_quote_hub_hardening.py`，以及原 V2-H2/I、Phase3A23、Yuanta contract。命令採 python -B -m pytest，獨立 MARKET_AI_DATA_ROOT / basetemp、禁 pytest cache；正式結果以 PR/本報告記錄為準。

## 尚未完成，不能誤報已修好

1. **執行中的舊 recorder 尚未由本輪停止或重啟。** 新保護是 disk source / offline verified，不是 live deployment。不要讓新 agent 同時登入。先確認舊 PID、最後持久化批次与無重複 owner，再安排可回復交接；無法證明舊 RAM 全寫出時不能承諾無縫零丟失。
2. 自動 reconnect、授權拒絕後生命週期、session/contract 自動 roll、durable spool/WAL 尚未實作。新 status 保守標 NOT_CONTINUOUSLY_VERIFIED、MANUAL_SINGLE_OWNER、BUFFERED_NOT_ZERO_LOSS；跨 UTC 日提示 CONTRACT_REVALIDATION_REQUIRED。這些是下一工作包，不能把 flags 當已實現。
3. recorder→V2-A.2→features/models→public packet 的 field-aware reader 尚未接通；logging 成功不等於模型在學習。現有舊錄製資料無 per-field provenance，不能自動補造時間或直接算高品質訓練資料。
4. Outcome horizon maturity / evaluation_as_of / homogeneous model-version-event scope 的端到端契約仍需 W3 補足。2I.1 描述性 pooled metrics 不可當 production calibration；公開 audit helper 已關閉，維持 fitting NOT STARTED。
5. 真實 OOS / forward / 校準與淨經濟優勢仍無本次新證據。ENGINE PASS ≠ CALIBRATED ≠ EDGE。
6. 新 Windows、重建 venv、WinCred/COM/合法 SDK/模型權重重新配置與恢復演練仍需 W7；不能整包複製就保證即用。

## 回復與下一棒

本輪保留原檔備份於交接工作區 repair_backup；正式回復依 Git 父基準 eb9202a 與修補 diff 逐項 review，不 reset 使用者其他變更。未改 DB schema、未登入/登出券商、未下單/查帳務、未下載模型、未啟用 AUTO_TRAIN。

下一棒先核對最新 HEAD/dirty/實際 runtime，以單一工作包完成受控 recorder 交接與 field-aware reader/replay；W3 到期與 scope 契約必須在 calibration fitting 之前。長期 Price/Probability Map 設計見 02_ROADMAP.md。
