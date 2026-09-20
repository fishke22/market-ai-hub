# Architecture（Phase 2）

## Interactive analysis path（使用者觸發）
```
Official Data Sources (JPX/BLS/Cboe/EDGAR/BOJ) + Proxy (yfinance/^N225)
        ↓
Smart Data Lake (automation/data_lake.py)   ← 增量、只補 missing range
        ↓
Data Quality (services/data_consistency.py)
        ↓
Feature Store (feature_store/store.py)
        ↓
Regime Engine (regime/engine.py) + Event Engine (regime/events.py)
        ↓
Direct Models (chronos/timesfm/xgboost/lightgbm/nhits/nbeatsx)
        ↓
Model Tournament (research/tournament/) → Best Baseline
        ↓
Joint Forecast (forecast/joint_baselines.py) + Scenario Engine (forecast/scenario.py)
        ↓
Dynamic Ensemble (forecast/dynamic_ensemble.py)
        ↓
Historical Edge (strategy/edge_store.py)
        ↓
Strategy Research State (strategy/output.py)
        ↓
Analysis Packet (packet/builder.py)  ← compact/normal/audit
        ↓
MCP (mcp/server.py) → Skills (skills/) → AI Client
```

## Background learning path（排程/背景，與 interactive 分離）
```
Prediction Registry (research/registry.py)
        ↓
Outcome Settlement (automation/loop.py settle_*)
        ↓
Performance Store (research/tournament/performance_store.py)
        ↓
Automated Research Loop (automation/loop.py 10 steps)
        ↓
Training Eligibility (automation/training_policy.py) → Challenger Retraining
        ↓
（只推薦 promotion，AUTO_PROMOTE_CHAMPION=false）
```

## 兩條路徑獨立
- interactive：即時、無 GPU 阻塞、provider 失敗 degrade。
- background：補資料/結算/重訓，GPU busy 時 defer。
