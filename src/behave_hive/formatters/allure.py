"""Allure formatter on top of allure-behave 2.16.2 internals (D7)."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

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
    from allure_commons.model2 import ATTACHMENT_PATTERN, Attachment, StatusDetails
    from allure_commons.model2 import Status as AllureStatus
    from allure_commons.types import AttachmentType
    from allure_commons.utils import get_testplan, now
    from behave.formatter.base import Formatter
except ImportError as exc:
    raise HiveError('the allure format needs allure-behave: pip install "behave-hive[allure]"') from exc

from behave_hive.privacy import scrub, user_home
from behave_hive.roots import PathMap
from behave_hive.selection import SelectionSnapshot

PATH_MAP_KEY = "behave_hive.path_map"
EXTENSIONS = {kind.mime_type: kind.extension for kind in AttachmentType}


class HiveAllureFileLogger(AllureFileLogger):
    """Sanitize diagnostics before any result or hook container is persisted."""

    def __init__(self, report_dir, listener):
        super().__init__(report_dir)
        self.listener = listener

    def _report_item(self, item):
        self.listener.scrub_result(item)
        super()._report_item(item)


class HiveAllureListener(AllureListener):
    """Never drops a result, turns hook failures into `broken` and reports original paths."""

    def __init__(self, behave_config):
        super().__init__(behave_config)
        raw = json.loads(behave_config.userdata.get(PATH_MAP_KEY) or "{}")
        self.path_map = PathMap({Path(expanded): Path(original) for expanded, original in raw.items()})
        self.has_path_map = bool(raw)

    def scrub_result(self, result):
        """Scrub status details recursively, including nested steps and fixtures."""
        details = getattr(result, "statusDetails", None)
        if details is not None:
            for key in ("message", "trace"):
                value = getattr(details, key)
                if value is not None:
                    setattr(details, key, scrub(value, self.path_map, Path.cwd(), user_home()))
        for key in ("steps", "befores", "afters"):
            for child in getattr(result, key, []):
                self.scrub_result(child)

    def attach_embedding(self, mime_type, data):
        """Attach `data` to the latest step of the current scenario, even when that step already ended."""
        test = self.logger.get_test(self.current_scenario_uuid)
        if test is None or not test.steps:
            return
        file_name = ATTACHMENT_PATTERN.format(prefix=uuid4(), ext=EXTENSIONS.get(mime_type, "attach"))
        test.steps[-1].attachments.append(Attachment(source=file_name, name=mime_type, type=mime_type))
        allure_commons.plugin_manager.hook.report_attached_data(body=data, file_name=file_name)

    def start_scenario(self, scenario):
        super().start_scenario(scenario)
        if self.has_path_map:
            result = self.logger.get_test(self.current_scenario_uuid)
            result.titlePath = self._title_path(scenario)

    def _title_path(self, scenario) -> list[str]:
        """Directory of the original `.feature` (relative to the cwd) followed by the feature name."""
        cwd = Path.cwd()
        filename = Path(scenario.filename)
        absolute = filename if filename.is_absolute() else cwd / filename
        original = self.path_map.to_original(absolute)
        with suppress(ValueError):
            original = original.relative_to(cwd)
        return [*original.parts[:-1], scenario.feature.name or original.name or scenario.feature.keyword]

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
        self.file_logger = HiveAllureFileLogger(self.stream_opener.name, self.listener)
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

    def embedding(self, mime_type, data):
        self.listener.attach_embedding(mime_type, data)
