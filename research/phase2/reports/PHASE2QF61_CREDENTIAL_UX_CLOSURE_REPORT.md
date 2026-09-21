# PHASE 2Q-F.6.1 — Credential UX Closure + WinCred Post-Install Verification

- gate：**PHASE2QF61_CREDENTIAL_UX_PASS**
- build_id：`1fa0f15a0764eb4f`（未變；本棒只改 scripts/tests，未改 runtime source）
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 9 問答（§17）

1. **為什麼當時只 prompt FinMind？** 因為執行時 FRED 已 configured → 腳本正確印 `FRED_API_KEY = ALREADY_CONFIGURED` 並 `continue`（Case B），只 prompt FinMind。這是**正確行為**，非 bug；但當時 UX 缺 `--status` 且 prompt 文字不友善，讓使用者誤以為 FRED 被漏掉。

2. **FRED prompt 為何沒有出現？** 同上：FRED 已 configured，被正確跳過（Case B）。已用測試 `test_setup_fred_exists_prompts_finmind_only` 證明。

3. **目前 canonical WinCred targets？** `MARKET_AI_HUB/FRED_API_KEY`、`MARKET_AI_HUB/FINMIND_API_TOKEN`（enumerate 確認存在）。另有 `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`（不碰）。

4. **central resolver 是否成功讀到兩個 configured entries？** 是。`secret_status` 兩者皆 `configured=True, source=WINCRED`。

5. **provider shallow status 是否仍 needs_config？** 否。設定後 FRED/FinMind `status()=ok`（credential-only 檢查，不打 network）。

6. **deep provider auth validation 結果？** FRED = OK；FinMind = OK（read-only 最小請求）。

7. **是否碰到任何 QROS credential？** **NO**（`secret_store` 只用 `MARKET_AI_HUB/` prefix；delete/set 皆限定 canonical targets；測試 `test_does_not_touch_qros_credentials` 證明）。

8. **是否碰到 Yuanta credentials？** **NO**（`test_does_not_touch_yuanta_credentials` 證明；只允許 FRED_API_KEY / FINMIND_API_TOKEN）。

9. **repo/log/report 是否 0 secrets？** 是。secret scan 0 真實 secret（4 誤報皆 getpass prompt）；git diff scan 無 secret 值。

## 交付

- `scripts/setup_api_credentials.py`：友善 prompt（`FRED API key:` / `FinMind API token:`）+ Case A/B/C/D + `--status` / `--replace fred|finmind|all` / `--delete fred|finmind`（只碰 MARKET_AI_HUB canonical targets）。
- `scripts/validate_provider_auth.py`（新）：deep read-only auth probe（不 leak token）。
- `tests/test_phase2qf61.py`（14 tests，fake backend）。
- 修 `test_fred_adapter_mock.py` / `test_finmind_adapter_mock.py`：改 mock resolver（不再依賴 env absence）。

## Verification

- `setup_api_credentials.py --status`：`FRED_API_KEY = CONFIGURED (source=WINCRED)`、`FINMIND_API_TOKEN = CONFIGURED (source=WINCRED)`。
- **full default pytest：831 passed, 20 deselected**（817 + 14 new）。
- secret scan PASS；git diff scan PASS。

## 安全

- Agent **未讀取/顯示/複製/log** 任何 credential value。
- Agent **未從 conversation 抽取**任何舊 key；只使用 existing WinCred entry。
- QROS/*、MARKET_AI_HUB/YUANTA/* 及其他 Credential Manager entries 完全未動。

## 禁區未動

不碰 forecast model / ensemble / market semantics / OOS / strategy / broker / Cherry prompt / tag / release / force push。
