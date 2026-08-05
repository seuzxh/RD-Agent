from copy import deepcopy
from pathlib import Path

from rdagent.app.qlib_rd_loop.conf import QUANT_PROP_SETTING

# Factor
from rdagent.components.coder.factor_coder.config import get_factor_env
from rdagent.components.coder.factor_coder.factor import (
    FactorExperiment,
    FactorFBWorkspace,
    FactorTask,
)

# Model
from rdagent.components.coder.model_coder.conf import get_model_env
from rdagent.components.coder.model_coder.model import (
    ModelExperiment,
    ModelFBWorkspace,
    ModelTask,
)
from rdagent.core.experiment import Task
from rdagent.core.scenario import Scenario
from rdagent.scenarios.qlib.experiment.utils import get_data_folder_intro
from rdagent.scenarios.qlib.experiment.workspace import QlibFBWorkspace
from rdagent.scenarios.shared.get_runtime_info import get_runtime_environment_by_env
from rdagent.utils.agent.tpl import T


class QlibFactorExperiment(FactorExperiment[FactorTask, QlibFBWorkspace, FactorFBWorkspace]):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.experiment_workspace = QlibFBWorkspace(template_folder_path=Path(__file__).parent / "factor_template")


class QlibModelExperiment(ModelExperiment[ModelTask, QlibFBWorkspace, ModelFBWorkspace]):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.experiment_workspace = QlibFBWorkspace(template_folder_path=Path(__file__).parent / "model_template")


class QlibQuantScenario(Scenario):
    def __init__(self) -> None:
        super().__init__()
        self._source_data = deepcopy(get_data_folder_intro())

        self._rich_style_description = deepcopy(T(".prompts:qlib_factor_rich_style_description").r())
        self._experiment_setting = deepcopy(
            T(".prompts:qlib_factor_experiment_setting").r(
                train_start=QUANT_PROP_SETTING.train_start,
                train_end=QUANT_PROP_SETTING.train_end,
                valid_start=QUANT_PROP_SETTING.valid_start,
                valid_end=QUANT_PROP_SETTING.valid_end,
                test_start=QUANT_PROP_SETTING.test_start,
                test_end=QUANT_PROP_SETTING.test_end,
            )
        )

    def background(self) -> str:
        """Combined background for quant scenario (factor + model)."""
        quant_background = "The background of the scenario is as follows:\n" + T(".prompts:qlib_quant_background").r(
            runtime_environment=self.get_runtime_environment(),
        )
        factor_background = "This time, I need your help with the research and development of the factor. The background of the factor scenario is as follows:\n" + T(
            ".prompts:qlib_factor_background"
        ).r(
            runtime_environment=self.get_runtime_environment(tag="factor"),
        )
        model_background = "This time, I need your help with the research and development of the model. The background of the model scenario is as follows:\n" + T(
            ".prompts:qlib_model_background"
        ).r(
            runtime_environment=self.get_runtime_environment(tag="model"),
        )
        return quant_background + "\n" + factor_background + "\n" + model_background

    def get_source_data_desc(self) -> str:
        return self._source_data

    def output_format(self) -> str:
        """Combined output format (factor + model)."""
        factor_output_format = (
            "The factor code should output the following format:\n" + T(".prompts:qlib_factor_output_format").r()
        )
        model_output_format = (
            "The model code should output the following format:\n" + T(".prompts:qlib_model_output_format").r()
        )
        return factor_output_format + "\n" + model_output_format

    def interface(self) -> str:
        """Combined interface description (factor + model)."""
        factor_interface = (
            "The factor code should be written in the following interface:\n" + T(".prompts:qlib_factor_interface").r()
        )
        model_interface = (
            "The model code should be written in the following interface:\n" + T(".prompts:qlib_model_interface").r()
        )
        return factor_interface + "\n" + model_interface

    def simulator(self) -> str:
        """Combined simulator description (factor + model)."""
        factor_simulator = "The factor code will be sent to the simulator:\n" + T(".prompts:qlib_factor_simulator").r()
        model_simulator = "The model code will be sent to the simulator:\n" + T(".prompts:qlib_model_simulator").r()
        return factor_simulator + "\n" + model_simulator

    @property
    def rich_style_description(self) -> str:
        return self._rich_style_description

    @property
    def experiment_setting(self) -> str:
        return self._experiment_setting

    def get_scenario_all_desc(
        self,
        task: Task | None = None,
        filtered_tag: str | None = None,
        simple_background: bool | None = None,
        action: str | None = None,
    ) -> str:
        def common_description() -> str:
            return f"""\n------Background of the scenario------
{self.background()}
------The source dataset you can use------
{self.get_source_data_desc()}
"""

        # TODO: There are still some issues with handling source_data here
        def source_data() -> str:
            return f"""
------The source data you can use------
{self.get_source_data_desc()}
"""

        def interface_desc() -> str:
            return f"""
------The interface you should follow to write the runnable code------
{self.interface()}
"""

        def output_desc() -> str:
            return f"""
------The output of your code should be in the format------
{self.output_format()}
"""

        def simulator_desc() -> str:
            return f"""
------The simulator user can use to test your solution------
{self.simulator()}
"""

        if simple_background:
            return common_description()
        elif filtered_tag in ("hypothesis_and_experiment", "feedback"):
            return common_description() + simulator_desc()
        elif filtered_tag in ("factor", "feature", "factors"):
            return common_description() + interface_desc() + output_desc() + simulator_desc()
        elif filtered_tag in ("model", "model tuning"):
            return common_description() + interface_desc() + output_desc() + simulator_desc()
        elif action in ("factor", "model"):
            return common_description() + interface_desc() + output_desc() + simulator_desc()

    def get_runtime_environment(self, tag: str = None) -> str:
        assert tag in [None, "factor", "model"]

        if tag is None or tag == "factor":
            # Use factor env to get the runtime environment
            factor_env = get_factor_env()
            factor_stdout = get_runtime_environment_by_env(env=factor_env)
            if tag == "factor":
                stdout = factor_stdout

        if tag is None or tag == "model":
            # Use model env to get the runtime environment
            model_env = get_model_env()
            model_stdout = get_runtime_environment_by_env(env=model_env)
            if tag == "model":
                stdout = model_stdout

        if tag is None:
            # Combine the outputs from both environments
            stdout = (
                "=== [Environment to generate the factors] ===\n"
                + factor_stdout.strip()
                + "\n\n=== [Environment to train the models] ===\n"
                + model_stdout.strip()
            )

        return stdout
