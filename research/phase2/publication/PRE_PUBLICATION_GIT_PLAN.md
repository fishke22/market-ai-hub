# PRE-PUBLICATION GIT PLAN

> 正式 GitHub publication 前的安全流程。**禁止 force push / history rewrite / delete tags。**

## 目標
- remote: `https://github.com/fishke22/market-ai-hub`
- branch: `main`（V1 已發布，HEAD `f707fdf`）

## 步驟（下一棒執行，本棒不 push）

1. **fetch remote**：`git fetch origin`（取得 remote 最新狀態）
2. **verify remote state**：`git log origin/main --oneline -5`（確認 V1 history 未變）
3. **backup remote main ref**：記錄 `origin/main` SHA（作為 rollback 基準）
4. **create publication branch**：`git checkout -b phase2-publication`（不直接在 main 施工）
5. **stage + commit**：分階段 commit（source / docs / configs / tests），遵守 .gitignore + PUBLICATION_EXCLUDE_MANIFEST
6. **push branch**：`git push -u origin phase2-publication`
7. **review diff**：`git diff origin/main...phase2-publication`（人工確認無 private/proprietary）
8. **merge normally**：`git merge`（不 squash 歷史，不 force）
9. **create release tag**：`git tag v2.0.0-rc1`（Phase 2 Research Release Candidate）

## 禁止
- `git push --force` / `git push -f`
- `git reset --hard`（會丟失未 commit 工作）
- `git clean -fd`（會刪除 untracked 檔案，含可能的重要報告）
- 刪除/rewrite V1 history / tags
- squash 合併歷史 provenance

## 前置確認（本棒已完成）
- secret scan：無 hardcoded credential（masked 報告）
- private data：data/ 僅 .gitkeep（無 225LABO raw/normalized 進 repo）
- proprietary Yuanta：無 .ocx/.dll/.cab/.pdf 進 repo
- clean clone：PASS（core import + MCP 21 tools + reconstruct_verify）
- 研究結論：無 profitable/trading edge 假宣稱
