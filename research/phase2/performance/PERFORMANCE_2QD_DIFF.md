# PERFORMANCE_2QD_DIFF

resource profile: DESKTOP_SAFE

| metric | before | after | delta | percent |
|--------|--------|-------|-------|---------|
| health_check first (sec) | 15.894 | 0.706 | -15.188 | **-95.6%** |
| health_check warm (sec) | 7.545 | 0.022 | -7.523 | **-99.7%** |
| get_system_info (sec) | 16.48 | 0.593 | -15.887 | **-96.4%** |
| get_research_gates (sec) | — | 0.139 | — | — |
| packet Osaka cold (sec) | 1.729 | 1.952 | +0.223 | +12.9%（warm 路徑無 regression） |
| packet Osaka warm (sec) | 0.0034 | 0.0033 | -0.0001 | -2.9% |
| packet Taiwan Stock cold (sec) | 0.529 | 0.554 | +0.025 | +4.7% |
| packet Taiwan Index cold (sec) | 0.205 | 0.205 | 0.0 | 0% |

- 主要改善：health / system_info / gates 不再 load 模型（shallow）。
- 未改動研究 truth；cache invalidation 以 data hash 為 primary。
- 未 regression（packet warm 持平）。
