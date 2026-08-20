"""
QuantaAlpha custom workspace.

Overrides rdagent QlibFBWorkspace: project-level factor_template overrides default YAML;
base files (read_exp_res.py, etc.) still from rdagent; init empty git repo in workspace to suppress qlib recorder git output.
"""

import subprocess
import re
from pathlib import Path

import pandas as pd

from rdagent.components.coder.model_coder.conf import MODEL_COSTEER_SETTINGS
from rdagent.scenarios.qlib.experiment.workspace import QlibFBWorkspace as _RdagentQlibFBWorkspace
from rdagent.log import rdagent_logger as logger
from rdagent.utils.env import QlibCondaConf, QlibCondaEnv, QTDockerEnv

_CUSTOM_TEMPLATE_DIR = Path(__file__).resolve().parent / "factor_template"


class QlibFBWorkspace(_RdagentQlibFBWorkspace):
    """
    Override rdagent QlibFBWorkspace: inject project factor_template/ YAML over defaults;
    init empty git repo in workspace to avoid qlib recorder git help output.
    """

    def __init__(self, template_folder_path: Path, *args, **kwargs) -> None:
        super().__init__(template_folder_path, *args, **kwargs)
        if _CUSTOM_TEMPLATE_DIR.exists():
            self.inject_code_from_folder(_CUSTOM_TEMPLATE_DIR)
            logger.info(f"Overrode rdagent default config with project template: {_CUSTOM_TEMPLATE_DIR}")

    def before_execute(self) -> None:
        """Init empty git repo in workspace to suppress qlib recorder git warnings."""
        super().before_execute()
        git_dir = self.workspace_path / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

    def execute(self, qlib_config_name: str = "conf.yaml", run_env: dict = {}, *args, **kwargs):
        """Run qlib and return metrics even when optional portfolio chart artifacts are absent."""
        timeout = kwargs.pop("timeout", None)
        if MODEL_COSTEER_SETTINGS.env_type == "docker":
            qtde = QTDockerEnv()
        elif MODEL_COSTEER_SETTINGS.env_type == "conda":
            qtde = QlibCondaEnv(conf=QlibCondaConf())
        else:
            logger.error(f"Unknown env_type: {MODEL_COSTEER_SETTINGS.env_type}")
            return None, "Unknown environment type"
        old_timeout = getattr(qtde.conf, "running_timeout_period", None)
        if timeout is not None:
            qtde.conf.running_timeout_period = int(timeout)
        qtde.prepare()

        try:
            execute_qlib_log = qtde.check_output(
                local_path=str(self.workspace_path),
                entry=f"qrun {qlib_config_name}",
                env=run_env,
            )
        finally:
            qtde.conf.running_timeout_period = old_timeout
        logger.log_object(execute_qlib_log, tag="Qlib_execute_log")

        execute_log = qtde.check_output(
            local_path=str(self.workspace_path),
            entry="python read_exp_res.py",
            env=run_env,
        )
        logger.log_object(execute_log, tag="Qlib_read_result_log")

        quantitative_backtesting_chart_path = self.workspace_path / "ret.pkl"
        if quantitative_backtesting_chart_path.exists():
            ret_df = pd.read_pickle(quantitative_backtesting_chart_path)
            logger.log_object(ret_df, tag="Quantitative Backtesting Chart")
        else:
            logger.warning("Optional portfolio chart file ret.pkl was not found; continuing with qlib metrics.")

        qlib_res_path = self.workspace_path / "qlib_res.csv"
        if qlib_res_path.exists():
            pattern = r"(Epoch\d+: train -[0-9\.]+, valid -[0-9\.]+|best score: -[0-9\.]+ @ \d+ epoch)"
            matches = re.findall(pattern, execute_qlib_log)
            if matches:
                execute_qlib_log = "\n".join(matches)
            result = pd.read_csv(qlib_res_path, index_col=0).iloc[:, 0]
            if result.dropna().empty:
                logger.warning(f"Qlib metrics file {qlib_res_path} is empty.")
            return result, execute_qlib_log

        logger.error(f"File {qlib_res_path} does not exist.")
        return None, execute_qlib_log
