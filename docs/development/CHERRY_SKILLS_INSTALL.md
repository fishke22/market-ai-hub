# Cherry Studio Skills 安裝

三個 Skill 位於 `cherry_skills/`，每個含 `SKILL.md`（繁體中文）。

```
cherry_skills/
  osaka-micro-analysis/SKILL.md   大阪微型日經分析
  taiwan-stock-v28/SKILL.md       台股分析
  model-validation-audit/SKILL.md 模型驗證稽核
```

## 安裝（Cherry Studio）
1. 將 `cherry_skills/<skill-name>/` 整個資料夾複製到 Cherry Studio 的 skill 目錄
   （依 Cherry Studio 版本，通常為 skills 資料夾）。
2. 或在 Cherry Studio 中直接建立 skill，把 `SKILL.md` 內容貼入。

## 使用方式
- 發問「分析大阪微型日經」→ 觸發 `osaka-micro-analysis`。
- 發問「分析 2330」→ 觸發 `taiwan-stock-v28`。
- 發問「稽核這個模型」→ 觸發 `model-validation-audit`。

## 原則
- Skill 只做「固定工作流程」，MCP 做計算。
- 不複製巨大 System Prompt。
- 數值一律由 `get_analysis_packet` / backend MCP 提供，LLM 不重複抓資料。
