# Yuanta Support Checklist（打給營業員/客服的詢問清單）

> 不要放實際帳號。直接照念：

1. 我的期貨帳號是否已開通 SPARK API 權限？
2. 是否已開通 API 行情服務？
3. 大阪微日經（JNU）的 SPARK 行情報價代碼是否為 `JNU<合約月>`（如 JNU2609）？（本機 FunctionList 已見此格式，向營業員雙重確認）
4. 大阪微日經是否支援 Legacy YuantaQuote COM 行情 API？
5. 若支援，AddMktReg 使用的完整 symbol 格式為何？
6. 海外期貨行情是否需要額外行情授權或費用？
7. 交易 API 權限目前是否已開通？

## 補充
- 證券 SPARK 已驗證（`MsgCode=0001`）。
- 期貨 SPARK 回 `0112`（無此權限使用功能）→ 確認是否已申請期貨 SPARK 權限。
- Legacy Quote COM 登入「T+1 盤成功、T 盤無登入權」→ 確認 T 盤行情權限。
