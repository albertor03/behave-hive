"""Which scenarios behave selected to run, computed inside the formatter (D5)."""

from __future__ import annotations

from behave.configuration import Configuration
from behave.model import Feature, Scenario


class SelectionSnapshot:
    """Scenarios of `feature` that behave selects, taken when the formatter sees the feature.

    Replicates behave's own selection (locations, tags and names) for any way of invoking
    it, so the formatter reports exactly what behave runs, even when used directly.
    """

    def __init__(self, feature: Feature, config: Configuration) -> None:
        self._selected = {
            id(s)
            for s in feature.walk_scenarios()
            if not s.should_skip
            and s.should_run_with_tags(config.tag_expression)
            and s.should_run_with_name_select(config)
        }

    def __contains__(self, scenario: Scenario) -> bool:
        return id(scenario) in self._selected
