# Taiwan Stock v28（台股分析）

## Purpose
分析台股個股（2330 / 3706.TW / 華邦電 等），沿用 Jerry V28：公司行動校正 + 證據分層 + 反證 + 失效條件。

## When to use
使用者要分析台股個股時。

## Required MCP
- `get_analysis_packet`（數值優先由 backend 提供）
- `analyze_taiwan_stock`（個股結構化證據）

## Workflow
1. 數值資料優先 `get_analysis_packet(market="taiwan", target="<代碼>", horizon="1d", detail_level="normal")`。
2. 需個別資料才呼叫 `analyze_taiwan_stock`。
3. 避免 LLM 自己重複抓資料。

## Required checks
- 公司行動校正（除權息/增減資/分割）後價格才可比。
- 主動找反證，不只看支持結論的資料。
- 明確失效條件。

## Output structure
- 偏多/偏空/盤整 + 主要區間 + 支撐/壓力 + 失效條件 + 重新分析時機。

## Failure handling
- 資料不足明說；不得編數字。

## Do not rules
- 不得製造假 probability。
- 不得以「感覺會漲」當理由，需有證據分層。
