"""Allure formatter on top of allure-behave 2.16.2 internals (D7)."""

from __future__ import annotations

from behave_hive.errors import HiveError

try:
    import allure_commons
    from allure_behave.formatter import AllureFormatter as BaseAllureFormatter
    from allure_behave.listener import AllureListener
    from allure_behave.utils import (
        is_planned_scenario,
        scenario_status,
        scenario_status_details,
    )
    from allure_commons.logger import AllureFileLogger
    from allure_commons.model2 import StatusDetails
    from allure_commons.model2 import Status as AllureStatus
    from allure_commons.utils import get_testplan, now
    from behave.formatter.base import Formatter
except ImportError as exc:  # pragma: no cover - exercised by monkeypatching sys.modules
    raise HiveError('the allure format needs allure-behave: pip install "behave-hive[allure]"') from exc

from behave_hive.selection import SelectionSnapshot


class HiveAllureListener(AllureListener):
    """Never drops a result and turns hook failures into `broken`."""

    def stop_scenario(self, scenario):
        status = scenario_status(scenario)
        details = scenario_status_details(scenario)
        if (scenario.hook_failed or scenario.status.name == "cleanup_error") and status == AllureStatus.PASSED:
            status = AllureStatus.BROKEN
            details = StatusDetails(message=getattr(scenario, "error_message", None) or "hook error")

        self.flush_steps()
        test_result = self.logger.get_test(self.current_scenario_uuid)
        test_result.stop = now()
        test_result.status = status
        test_result.statusDetails = details
        self.logger.close_test(self.current_scenario_uuid)
        self.current_step_uuid = None
        self.group_context.append_test(self.current_scenario_uuid)
        self.group_context.exit()
        self.current_scenario_uuid = None


class AllureFormatter(BaseAllureFormatter):
    """One Allure result per scenario that behave selected, including `Rule` scenarios."""

    def __init__(self, stream_opener, config):
        Formatter.__init__(self, stream_opener, config)
        self.listener = HiveAllureListener(config)
        self.file_logger = AllureFileLogger(self.stream_opener.name)
        allure_commons.plugin_manager.register(self.listener)
        allure_commons.plugin_manager.register(self.file_logger)
        self.testplan = get_testplan()
        self._snapshot = None
        self._on = False

    def feature(self, feature):
        self._snapshot = SelectionSnapshot(feature, self.config)
        for scenario in feature.walk_scenarios():
            if scenario in self._snapshot:
                scenario.run = allure_commons.test(scenario.run, context={"scenario": scenario})
                is_planned_scenario(scenario, self.testplan)

    def scenario(self, scenario):
        self._on = scenario in self._snapshot

    def step(self, step):
        if self._on:
            super().step(step)

    def match(self, match):
        if self._on:
            super().match(match)

    def result(self, result):
        if self._on:
            super().result(result)
