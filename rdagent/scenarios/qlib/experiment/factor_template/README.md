| RD-Agent(Q) QLib Factor Config File                        | Description                                                                    |
|------------------------------------------------------------|--------------------------------------------------------------------------------|
| `factor_template/conf_baseline.yaml`                       | Baseline factors (e.g., Alpha20) with the GBDT model                           |
| `factor_template/conf_combined_factors.yaml`               | Merged SOTA and newly generated factors with the GBDT model                    |
| `factor_template/conf_combined_factors_sota_model.yaml`    | Merged SOTA and newly generated factors with the SoTA-trace-selected model     |

## Model selector

`conf_baseline.yaml` and `conf_combined_factors.yaml` are parameterized by a `model_selector` Jinja variable (rendered by `qrun` from the `QLIB_FACTOR_MODEL_SELECTOR` env var, default `lgbm`). The `task.model` block switches accordingly:

| `model_selector` | model class | module_path | notes |
|---|---|---|---|
| `lgbm` (default) | `LGBModel` | `qlib.contrib.model.gbdt` | LightGBM, current default behavior |
| `linear` | `LinearModel` | `qlib.contrib.model.linear` | closed-form OLS, fastest baseline |
| `xgboost` | `XGBModel` | `qlib.contrib.model.xgboost` | gradient boosting tree |
| `catboost` | `CatBoostModel` | `qlib.contrib.model.catboost_model` | gradient boosting tree (auto GPU/CPU; needs `pip install catboost`) |

`conf_combined_factors_sota_model.yaml` is **not** affected by `model_selector` — it always uses `GeneralPTNN` and is only selected by the factor runner when a `QlibModelExperiment` exists in the trace (Quant scenario).