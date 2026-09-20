# Phase 2Y-G.1 — Legacy Quote Session Diagnostic Correction

- Gate: **PHASE2YG1_PASS**（parser 修正 + TCP probe + session-aware 政策完成）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**494 passed**（484 + 10 2Y-G.1；5 live deselected）

## 重要修正：TLinkStatus 語義（官方 Quote API 文件）
| Status | 意義 |
|---|---|
| -2 | **LinkFail（網路連線失敗）** ← 不是 permission denied |
| -1 | LinkBroken |
| 0 | Idle |
| 1 | Connected |
| 2 | **LogonOK（登入成功）** |

**Msg[0]=='3' 才代表「無權限」（PERMISSION_DENIED）。**

先前把 status=-2 翻譯成「無登入權」是**錯誤解讀**，已修正。

## 實測證據重新分類（正確語義）
| 事件 | 舊（錯） | 新（對） |
|---|---|---|
| T+1 盤 status=2, msg="0行情連線登入成功" | 登入成功 | **LogonOK（SERVER_CONFIRMED）** |
| T 盤 status=-2, msg="3使用者無登入權限" | 無登入權 | **LinkFail + Msg[0]=3**（link 失敗 + 無權限碼）→ 需 session-aware retest |

## 已修正/交付
1. **Event parser**：每事件分存 `req_type / status / status_label / message_code /
   message_category / sanitized_message / received_at`。
2. **Login 判定**：Status=2 → SUCCESS；Msg[0]=3 → PERMISSION_DENIED；
   Status=-2 無 Msg[0]=3 → LINK_FAIL（非權限）。
3. **TCP probe**：`scripts/check_yuanta_quote_endpoints.ps1`（NO-AUTH，只測
   T 80/443 + T+1 82/442 的 TCP reachable；不含 credential）。
4. **Endpoint matrix**：T=reqType 1/ports 80,443；T+1=reqType 2/ports 82,442（官方 C# sample 一致）。
5. **Session-aware 政策**：T 真實 probe 只在正常交易日 T session 時段執行；
   T 狀態 = **REQUIRES_SESSION_AWARE_RETEST**（未定案 session permission）。
6. **Branch 規則**：SetMktLogon 無 branch-code parameter；禁止 brute-force branch/prefix。
   （Legacy Trading API 的歸戶 ID + OnLogonS AccList 才是未來 authoritative branch/account 來源，本棒不啟動。）

## Tests（10 新增）
legacy_status_minus2_is_link_failure / legacy_msg3_is_permission_denied /
legacy_status2_is_authenticated / legacy_same_login_id_for_t_and_tplus1 /
legacy_no_branch_login_parameter / no_branch_code_bruteforce /
endpoint_matrix_matches_official_sample / tcp_probe_has_no_credentials /
session_aware_retest_required / trading_api_account_metadata_flow_documented。

## 下一步（需使用者，正常 T session 時段）
1. 台灣時間 08:45–13:45（T 盤）執行 `scripts\yuanta_futures_auth.ps1`（已只提示密碼）。
2. 若 Msg[0]=3 → T_PERMISSION_DENIED_SERVER_CONFIRMED。
3. 若 Status=2 → T 盤 SUCCESS（先前只是盤外 LinkFail）。

## 驗證
- `pytest tests/ -q` → 493 passed
- sidecar import OK
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未 login（本棒）、未 order、未 recorder、未 GitHub push。
