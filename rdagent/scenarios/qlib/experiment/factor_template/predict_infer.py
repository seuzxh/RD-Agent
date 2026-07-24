#!/usr/bin/env python3
"""
predict_infer.py — 路径 1 五步预测 pipeline

在 docker(local_qlib:v2.1)内执行,消费 rdagent SOTA 产物,产出 T 日 Top20。

五步:
  A. 导行情(qlib bin → daily_pv.h5,基于 parquet 末日的空缺区间)
  B. 算因子(循环跑 sota factor.py)
  C. 补齐 parquet(concat 新旧因子值)
  D. 简化 inference(Alpha158DL + StaticDataLoader 手动 concat + 矩阵乘法)
  E. 保存预测回 pred.pkl(增量水位线)

用法(docker 内):
  python predict_infer.py --workspace /workspace/qlib_workspace --factors-dir /tmp/factors
"""
import argparse
import glob
import json
import os
import pickle
import shutil
import sys
from pathlib import Path

import pandas as pd


def step_a_export_quotes(workspace_path: str, gap_start, qlib_latest, lookback_days: int = 30):
    """A. 从 qlib bin 导出空缺区间的行情到 daily_pv.h5"""
    from qlib.data import D

    pv_start = (pd.Timestamp(gap_start) - pd.Timedelta(days=lookback_days)).date()
    instruments = D.instruments(market="all")
    fields = ["$open", "$close", "$high", "$low", "$volume", "$factor"]
    print(f"  [A] 导出行情 {pv_start} ~ {qlib_latest.date()} (lookback={lookback_days}天)")
    data = D.features(instruments, fields, start_time=str(pv_start), end_time=str(qlib_latest.date()), freq="day")
    # generate.py 用 swaplevel + sort_index 转成 (datetime, instrument)
    data = data.swaplevel().sort_index()
    pv_path = os.path.join(workspace_path, "daily_pv.h5")
    data.to_hdf(pv_path, key="data")
    print(f"  [A] shape={data.shape}, 日期 {data.index.get_level_values(0).min().date()} ~ {data.index.get_level_values(0).max().date()}")
    return pv_path


def step_b_compute_factors(workspace_path: str, factor_codes: list):
    """B. 循环跑每个 factor.py,收集新因子值"""
    os.chdir(workspace_path)
    new_factors = {}
    for i, (fname, code) in enumerate(factor_codes):
        print(f"  [B] 跑因子 {i+1}/{len(factor_codes)}: {fname}")
        result_path = os.path.join(workspace_path, "result.h5")
        if os.path.exists(result_path):
            os.remove(result_path)
        try:
            exec(compile(code, f"{fname}.py", "exec"), {"__name__": "__main__"})
            if os.path.exists(result_path):
                result = pd.read_hdf(result_path, key="data")
                new_factors[fname] = result
                n_valid = result.notna().sum().iloc[0] if hasattr(result, "iloc") else result.notna().sum()
                print(f"      shape={result.shape}, 末日非空={n_valid}")
            else:
                print(f"      ⚠️ result.h5 未生成,跳过 {fname}")
        except Exception as e:
            print(f"      ⚠️ 因子 {fname} 执行失败: {e}")
    return new_factors


def step_c_merge_parquet(workspace_path: str, new_factors: dict):
    """C. 合并新因子值到 combined_factors_df.parquet"""
    parquet_path = os.path.join(workspace_path, "combined_factors_df.parquet")
    old = pd.read_parquet(parquet_path)
    old_end = old.index.get_level_values(0).max()
    print(f"  [C] 旧 parquet 末日: {old_end.date()}, shape={old.shape}")

    new_dfs = []
    for fname, result in new_factors.items():
        if isinstance(result, pd.Series):
            result = result.to_frame()
        if not isinstance(result.columns, pd.MultiIndex):
            result.columns = pd.MultiIndex.from_product([["feature"], result.columns])
        new_dfs.append(result)

    if not new_dfs:
        print("  [C] ⚠️ 无新因子值,跳过合并")
        return parquet_path

    new_all = pd.concat(new_dfs, axis=1)
    new_all = new_all[new_all.index.get_level_values(0) > old_end]
    print(f"  [C] 新因子值 shape={new_all.shape}, 日期 {new_all.index.get_level_values(0).min().date() if len(new_all)>0 else 'N/A'} ~ {new_all.index.get_level_values(0).max().date() if len(new_all)>0 else 'N/A'}")

    if len(new_all) == 0:
        print("  [C] 无新日期数据,跳过合并")
        return parquet_path

    merged = pd.concat([old, new_all]).sort_index()
    tmp_path = parquet_path + ".tmp"
    merged.to_parquet(tmp_path)
    os.replace(tmp_path, parquet_path)
    print(f"  [C] 合并后 shape={merged.shape}, 末日={merged.index.get_level_values(0).max().date()}")
    return parquet_path


def step_d_inference(workspace_path: str, qlib_latest):
    """D. 简化 inference:手动 concat feature + 矩阵乘法"""
    import copy
    from qlib.contrib.data.loader import Alpha158DL
    from qlib.data.dataset.loader import StaticDataLoader

    task = pickle.load(open(glob.glob(os.path.join(workspace_path, "mlruns/*/*/artifacts/task"))[0], "rb"))
    loaders = task["dataset"]["kwargs"]["handler"]["kwargs"]["data_loader"]["kwargs"]["dataloader_l"]

    # 加载 Alpha158 feature(去掉 label)
    a158_cfg = copy.deepcopy(loaders[0]["kwargs"]["config"])
    a158_cfg.pop("label", None)
    hk = task["dataset"]["kwargs"]["handler"]["kwargs"]
    d0 = Alpha158DL(config=a158_cfg).load(None, hk["start_time"], str(qlib_latest.date()))

    # 加载 SOTA 因子(从补齐后的 parquet)
    d1 = StaticDataLoader(config=loaders[1]["kwargs"]["config"]).load()

    # 合并 + 列排序
    features = pd.concat([d0, d1], axis=1).sort_index().sort_index(axis=1)
    print(f"  [D] feature shape: {features.shape}, 末日: {features.index.get_level_values(0).max().date()}")

    # 检查列数和 model coef_ 匹配
    model = pickle.load(open(glob.glob(os.path.join(workspace_path, "mlruns/*/*/artifacts/params.pkl"))[0], "rb"))
    print(f"  [D] model: {type(model).__name__}")

    # 矩阵乘法
    if hasattr(model, "coef_"):  # LinearModel
        if features.shape[1] != len(model.coef_):
            print(f"  [D] ⚠️ 列数不匹配: feature={features.shape[1]} vs coef_={len(model.coef_)}")
        scores = features.values @ model.coef_ + model.intercept_
    elif hasattr(model, "model"):  # LGBModel
        scores = model.model.predict(features.values)
    else:
        raise ValueError(f"unknown model type: {type(model)}")

    pred = pd.Series(scores, index=features.index)
    print(f"  [D] pred shape: {pred.shape}, 末日: {pred.index.get_level_values(0).max().date()}")
    return pred, features


def step_e_save_pred(workspace_path: str, new_pred: pd.Series):
    """E. 保存预测回 pred.pkl(增量追加)"""
    pred_path = glob.glob(os.path.join(workspace_path, "mlruns/*/*/artifacts/pred.pkl"))[0]
    old_pred = pickle.load(open(pred_path, "rb"))
    pred_end = old_pred.index.get_level_values(0).max()
    new_part = new_pred[new_pred.index.get_level_values(0) > pred_end]
    if len(new_part) == 0:
        print("  [E] 无新预测需追加")
        return old_pred
    new_df = new_part.to_frame("score")
    merged = pd.concat([old_pred, new_df]).sort_index()
    # 去重(同一日期保留新的)
    merged = merged[~merged.index.duplicated(keep="last")]
    tmp_path = pred_path + ".tmp"
    with open(tmp_path, "wb") as f:
        pickle.dump(merged, f)
    os.replace(tmp_path, pred_path)
    print(f"  [E] pred.pkl 更新: 追加 {len(new_part)} 行, 末日={merged.index.get_level_values(0).max().date()}")
    return merged


def load_factor_codes(factors_dir: str):
    """从目录加载因子代码"""
    result = []
    for py in sorted(Path(factors_dir).glob("*.py")):
        if py.name.startswith("_"):
            continue
        result.append((py.stem, py.read_text()))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, help="SOTA workspace 路径")
    parser.add_argument("--factors-dir", required=True, help="因子代码目录")
    parser.add_argument("--lookback", type=int, default=30, help="导行情的 lookback 天数")
    args = parser.parse_args()

    import qlib
    from qlib.constant import REG_CN

    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)
    from qlib.data import D

    ws = args.workspace
    os.chdir(ws)

    # 加载因子代码
    factor_codes = load_factor_codes(args.factors_dir)
    print(f"因子数: {len(factor_codes)}, 名称: {[f[0] for f in factor_codes]}")

    # 算时间范围(基于 parquet 末日)
    old_factors = pd.read_parquet(os.path.join(ws, "combined_factors_df.parquet"))
    parquet_end = old_factors.index.get_level_values(0).max()
    qlib_latest = pd.Timestamp(D.calendar(freq="day")[-1])
    print(f"\n=== 时间范围 ===")
    print(f"  parquet 末日: {parquet_end.date()}")
    print(f"  qlib 最新(T日): {qlib_latest.date()}")

    if parquet_end >= qlib_latest:
        print("  因子值已到 T 日,直接用已有 pred")
        old_pred = pickle.load(open(glob.glob(os.path.join(ws, "mlruns/*/*/artifacts/pred.pkl"))[0], "rb"))
        pred_end = old_pred.index.get_level_values(0).max()
        if pred_end >= qlib_latest:
            top20 = old_pred.xs(pred_end, level=0).dropna().sort_values("score", ascending=False).head(20)
        else:
            # parquet 到 T 日但 pred 没到,需要重新 D 步
            print("  pred 未到 T 日,执行 D 步...")
            pred, features = step_d_inference(ws, qlib_latest)
            pred = step_e_save_pred(ws, pred)
            top20 = pred.xs(qlib_latest, level=0).dropna().sort_values(ascending=False).head(20)

        result = {
            "predict_date": str(top20.index[0] if hasattr(top20.index[0], "year") else qlib_latest.date()),
            "top20": [{"rank": i + 1, "instrument": code, "score": float(score)} for i, (code, score) in enumerate(top20.items())],
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    # ===== A. 导行情 =====
    print(f"\n=== 步骤 A: 导行情 ===")
    step_a_export_quotes(ws, parquet_end + pd.Timedelta(days=1), qlib_latest, args.lookback)

    # ===== B. 算因子 =====
    print(f"\n=== 步骤 B: 算因子 ===")
    new_factors = step_b_compute_factors(ws, factor_codes)

    # ===== C. 补齐 parquet =====
    print(f"\n=== 步骤 C: 补齐 parquet ===")
    step_c_merge_parquet(ws, new_factors)

    # ===== D. 简化 inference =====
    print(f"\n=== 步骤 D: 简化 inference ===")
    pred, features = step_d_inference(ws, qlib_latest)

    # ===== E. 保存预测回 pred.pkl =====
    print(f"\n=== 步骤 E: 保存 pred.pkl ===")
    pred = step_e_save_pred(ws, pred)

    # ===== 输出 Top20 =====
    final_day = pred.index.get_level_values(0).max()
    last_day_data = pred.xs(final_day, level=0)

    # 统一转成 Series(code → score)
    if isinstance(last_day_data, pd.DataFrame):
        score_col = "score" if "score" in last_day_data.columns else last_day_data.columns[0]
        last_series = last_day_data[score_col].dropna()
    else:
        last_series = last_day_data.dropna()

    top20 = last_series.sort_values(ascending=False).head(20)

    print(f"\n{'='*60}")
    print(f"=== 预测完成 ===")
    print(f"预测日期: {final_day.date()}")
    print(f"Top20:")
    for i, (code, score) in enumerate(top20.items(), 1):
        print(f"  {i:2d}. {code}  {score:.6f}")

    result = {
        "predict_date": str(final_day.date()),
        "top20": [{"rank": i + 1, "instrument": code, "score": float(score)} for i, (code, score) in enumerate(top20.items())],
    }
    print(f"\n=== JSON ===")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
