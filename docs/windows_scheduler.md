# Windows 排程（opt-in）

**不自動註冊**。使用者手動執行一次：

```powershell
# 註冊（建立 2 個 Scheduled Task）
.\scripts\register_research_tasks.ps1

# 移除
.\scripts\unregister_research_tasks.ps1
```

## 建立的工作
| Task | 時間 |
|---|---|
| MARKET_AI_HUB_ResearchTick | 每週一 09:00（tick） |
| MARKET_AI_HUB_DataSync | 每週一 08:30（sync_market_data） |

## 檢視
```powershell
Get-ScheduledTask -TaskName 'MARKET_AI_HUB_*'
```

## 電力 / 離線
- 筆電關機 → 下次開機 `catchup` 補追。
- 只允許 CPU 輕量工作進排程；重訓練（GPU）必須手動觸發，避免使用者不在時鎖 GPU。
