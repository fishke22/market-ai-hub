# Skills Reference

## Skill ≠ MCP ≠ LLM
- **MCP**：資料與計算（`get_analysis_packet` 等）。
- **Skill**：固定分析流程（SKILL.md）。
- **LLM**：理解與白話表達。

## 三個 Skills
| Skill | 用途 |
|---|---|
| `osaka-micro-analysis` | 大阪微型日經（TARGET = OSE Micro） |
| `taiwan-stock-v28` | 台股（公司行動校正 + 證據分層） |
| `model-validation-audit` | 模型驗證稽核 |

位置：`skills/{name}/SKILL.md`。

## 安裝
1. 複製 `skills/{name}/` 到 Agent 平台的 skill 目錄。
2. 或直接當 Agent instruction reference。

## 複製 / 更新 / 驗證
- 每個 SKILL.md 獨立、可搬移、不依賴聊天記憶。
- 更新：改 `skills/{name}/SKILL.md`。
- 驗證：`pytest tests/test_phase2ib.py`（skill_files_present / skill_required_mcp_valid）。

## 不支援 Skill 機制的平台
把 `SKILL.md` 內容貼為 Agent 的 system instruction / knowledge reference。
