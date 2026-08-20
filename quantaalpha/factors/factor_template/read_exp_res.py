from pathlib import Path

import pandas as pd
import qlib

qlib.init()

from qlib.workflow import R


experiments = R.list_experiments()

latest_recorder = None
for experiment in experiments:
    recorders = R.list_recorders(experiment_name=experiment)
    for recorder_id in recorders:
        if recorder_id is None:
            continue
        recorder = R.get_recorder(recorder_id=recorder_id, experiment_name=experiment)
        end_time = recorder.info.get("end_time")
        if end_time is None:
            print(f"Warning: Recorder {recorder_id} has no valid end time")
            continue
        if latest_recorder is None or end_time > latest_recorder.info.get("end_time", 0):
            latest_recorder = recorder

if latest_recorder is None:
    print("No recorders found")
else:
    print(f"Latest recorder: {latest_recorder}")

    metrics = pd.Series(latest_recorder.list_metrics())
    output_path = Path(__file__).resolve().parent / "qlib_res.csv"
    metrics.to_csv(output_path)
    print(f"Metrics have been saved to {output_path}")

    try:
        ret_data_frame = latest_recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        ret_data_frame.to_pickle("ret.pkl")
        print("Portfolio report has been saved to ret.pkl")
    except Exception as exc:
        print(f"Warning: portfolio report is unavailable: {exc}")
