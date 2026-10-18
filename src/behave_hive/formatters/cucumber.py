"""behave formatter that writes Cucumber JSON (D6). Usable without behave-hive."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import traceback
import unicodedata
from contextlib import suppress
from pathlib import Path

from behave.formatter.base import Formatter
from behave.model import ScenarioOutlineBuilder

from behave_hive.selection import SelectionSnapshot
from behave_hive.status import map_status, scenario_status


def _run_slot() -> dict[str, int]:
    """`worker` and `batch` from the environment set by the runner; empty when not a number."""
    slot = {"worker": os.environ.get("BEHAVE_HIVE_WORKER", ""), "batch": os.environ.get("BEHAVE_HIVE_BATCH", "")}
    return {key: int(value) for key, value in slot.items() if value.isdigit()}


def slug(text: str, default: str = "scenario") -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-") or default


def feature_id(uri: str) -> str:
    return f"{slug(uri, 'feature')}-{hashlib.sha256(uri.encode()).hexdigest()[:8]}"


def relative_uri(filename: str) -> str:
    path = Path(filename)
    if path.is_absolute():
        with suppress(ValueError):
            path = path.relative_to(Path.cwd())
    return path.as_posix()


class CucumberJSONFormatter(Formatter):
    name = "cucumber.json"
    description = "Cucumber JSON, one array of features (behave-hive)"

    def __init__(self, stream_opener, config):
        super().__init__(stream_opener, config)
        self.output = stream_opener.name
        self.features: list[dict] = []
        self._feature = None
        self._snapshot = None
        self._steps: list = []
        self._idx = -1
        self._locations: dict[int, str] = {}
        self._embeddings: dict[int, list[dict]] = {}

    # -- behave callbacks ---------------------------------------------------------

    def feature(self, feature):
        self._feature = feature
        self._snapshot = SelectionSnapshot(feature, self.config)
        self._locations = {}
        self._embeddings = {}

    def scenario(self, scenario):
        self._steps = list(scenario.all_steps)
        self._idx = -1

    def match(self, match):
        self._idx += 1
        location = getattr(match, "location", None)
        if location and 0 <= self._idx < len(self._steps):
            self._locations[id(self._steps[self._idx])] = str(location)

    def embedding(self, mime_type, data):
        if not self._steps:
            return
        index = self._idx if 0 <= self._idx < len(self._steps) else len(self._steps) - 1
        raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
        self._embeddings.setdefault(id(self._steps[index]), []).append(
            {"mime_type": mime_type, "data": base64.b64encode(raw).decode("ascii")}
        )

    def eof(self):
        feature = self._feature
        if feature is None:
            return
        elements = self._elements(feature)
        if elements:
            uri = relative_uri(feature.filename)
            self.features.append(
                {
                    "uri": uri,
                    "id": feature_id(uri),
                    "keyword": feature.keyword,
                    "name": feature.name,
                    "description": "\n".join(feature.description),
                    "line": feature.line,
                    "tags": [{"name": f"@{t}", "line": t.line} for t in feature.tags],
                    "elements": elements,
                }
            )
        self._feature = None

    def close(self):
        if self.output:
            tmp = f"{self.output}.tmp"
            directory = os.path.dirname(self.output)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.features, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.output)
        else:
            json.dump(self.features, self.stream, ensure_ascii=False, indent=2)
        super().close()

    # -- serialization ------------------------------------------------------------

    def _containers(self, feature):
        """Maps id(scenario or outline row) to its (outline, row number, rule) context."""
        context = {}
        for item in feature.run_items:
            if hasattr(item, "run_items"):  # Rule
                for inner in item.run_items:
                    self._register(context, inner, item)
            else:
                self._register(context, item, None)
        return context

    @staticmethod
    def _register(context, item, rule):
        if hasattr(item, "examples"):  # ScenarioOutline
            for n, row in enumerate(item.scenarios, start=1):
                context[id(row)] = (item, n, rule)
        else:
            context[id(item)] = (None, None, rule)

    def _elements(self, feature):
        context = self._containers(feature)
        feature_uri = relative_uri(feature.filename)
        fid = feature_id(feature_uri)
        elements = []
        for scenario in feature.walk_scenarios():
            if scenario not in self._snapshot:
                continue
            outline, n, rule = context.get(id(scenario), (None, None, None))
            steps = list(scenario.all_steps)
            background = self._background(feature, rule, scenario)
            if background is not None:
                elements.append(background)
            elements.append(self._scenario(feature, fid, scenario, outline, n, rule, steps))
        return elements

    def _background(self, feature, rule, scenario):
        if not scenario.background_steps:
            return None
        own = rule.background if rule is not None else None
        source = own if own is not None and len(own.steps) > 0 else feature.background
        return {
            "keyword": source.keyword,
            "name": source.name,
            "description": "",
            "line": source.line,
            "type": "background",
            "steps": [self._step(s) for s in scenario.background_steps],
        }

    def _scenario(self, feature, fid, scenario, outline, n, rule, steps):
        owner = outline or scenario
        scenario_id = f"{fid};{slug(owner.name)}-l{owner.line}" + (f";;{n}" if outline else "")
        own_steps = list(scenario.steps)
        status = scenario_status(scenario, steps)
        element = {
            "id": scenario_id,
            "keyword": scenario.keyword,
            "name": scenario.name,
            "description": "\n".join(scenario.description),
            "line": scenario.line,
            "type": "scenario",
            "tags": self._tags(feature, rule, scenario, outline),
            "steps": [self._step(s) for s in own_steps],
            "x-behave-hive": {"status": status, "behave_status": scenario.status.name, **_run_slot()},
        }
        self._hook_elements(element, scenario, steps)
        return element

    def _hook_elements(self, element, scenario, steps):
        cleanup_failed = scenario.status.name == "cleanup_error"
        if not (scenario.hook_failed or cleanup_failed):
            return
        if any(map_status(s.status) == "failed" for s in steps):
            return
        ran = any(s.status.name not in ("skipped", "untested") for s in steps)
        message = getattr(scenario, "error_message", None) or ("cleanup error" if cleanup_failed else "hook error")
        hook = [{
            "match": {"location": "environment.py"},
            "result": {"status": "failed", "duration": 0, "error_message": message},
        }]
        element["after" if (ran or cleanup_failed) else "before"] = hook

    def _tags(self, feature, rule, scenario, outline):
        tags: dict[str, int] = {}

        def add(name, line):
            tags.setdefault(name, line)

        for tag in feature.tags:
            add(str(tag), tag.line)
        if rule is not None:
            for tag in rule.tags:
                add(str(tag), tag.line)
        if outline is None:
            for tag in scenario.tags:
                add(str(tag), tag.line)
        else:
            row = scenario._row
            examples = next(ex for ex in outline.examples if any(r is row for r in ex.table.rows))
            base = {"examples.index": str(examples.index), "row.index": str(row.index), "row.id": row.id}
            base["examples.name"] = ScenarioOutlineBuilder.render_template(
                examples.name or "", row, dict(base, **{"examples.name": examples.name or ""})
            )
            for template in (*outline.tags, *examples.tags):
                for name in ScenarioOutlineBuilder.make_row_tags([template], row, base):
                    add(str(name), template.line)
        return [{"name": f"@{name}", "line": line} for name, line in tags.items()]

    @staticmethod
    def _error_message(step) -> str:
        """behave's message plus the traceback, which behave only adds with --verbose."""
        message = step.error_message or ""
        exception = getattr(step, "exception", None)
        if exception is not None and "Traceback" not in message:
            tb = "".join(traceback.format_exception(type(exception), exception, getattr(step, "exc_traceback", None)))
            message = f"{message}\n{tb}".strip()
        return message

    def _step(self, step):
        status = map_status(step.status)
        result = {"status": status, "duration": round((step.duration or 0) * 1e9)}
        if status == "failed":
            result["error_message"] = self._error_message(step)
        data = {
            "keyword": step.keyword.rstrip() + " ",
            "name": step.name,
            "line": step.line,
            "result": result,
        }
        location = self._locations.get(id(step))
        if location:
            data["match"] = {"location": location}
        if step.table:
            data["rows"] = [{"cells": list(step.table.headings)}] + [
                {"cells": list(r.cells)} for r in step.table.rows
            ]
        if step.text:
            data["doc_string"] = {
                "value": str(step.text),
                "content_type": step.text.content_type or "",
                "line": step.text.line,
            }
        if id(step) in self._embeddings:
            data["embeddings"] = self._embeddings[id(step)]
        return data
