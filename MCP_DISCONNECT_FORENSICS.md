# MCP Disconnect Forensics

**Phase 2Q-A §24** — 記錄 Cherry Studio 最後一次出現 `MCP connection interrupted` 的檢查結果。

## 檢查項目與發現

| 檢查項 | 位置 / 方法 | 發現 |
|--------|------------|------|
| MCP logs | `logs/mcp.log` | 僅 HF Hub unauthenticated warnings，無 traceback / ERROR |
| process exit / stderr / traceback | 無 crash dump、無 Python traceback 於 log | 未發現 |
| OOM | 無 OOM killer / MemoryError 紀錄 | 未發現 |
| VRAM | 無 CUDA OOM 紀錄 | 未發現 |
| timeout | 無明確 MCP timeout 事件 | 未發現 |
| stdio pipe close | 無 server 端 stdout/stderr 寫入失敗紀錄 | 未發現 |
| client cancellation | Cherry Studio 端無可取得證據 | 未發現（client-side，本倉庫無權讀取） |

## 結論

**UNKNOWN**。

無本倉庫可取得的證據足以歸因於 GPU / Cherry Studio / network 任一特定原因。
不猜測、不歸咎。

## 下一步驗證（最小）

1. 重現時開啟 `MCP_PERF_TRACE=true`，觀察最後一次 tool call 的 `server_latency_ms` 是否異常偏高。
2. 檢查 Cherry Studio 端 MCP client log（非本倉庫）。
3. 觀察是否在 model 載入（Chronos/TimesFM）階段中斷 → 指向 cold-start 載入時間。
