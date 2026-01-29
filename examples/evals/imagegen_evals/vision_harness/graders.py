from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from openai import OpenAI

from .io import image_to_data_url
from .types import ModelResponse, Score, TestCase


class Grader(Protocol):
    key: str

    def grade(self, response: ModelResponse, case: TestCase) -> Score | list[Score]: ...


def pick_first_image(response: ModelResponse) -> Optional[Path]:
    for artifact in response.artifacts:
        if artifact.kind == "image":
            return artifact.path
    return None


def build_generation_judge_content(case: TestCase, output_image: Path) -> list[dict]:
    return [
        {
            "type": "input_text",
            "text": f"Prompt:\n{case.prompt}\n\nCriteria:\n{case.criteria}",
        },
        {
            "type": "input_image",
            "image_url": image_to_data_url(output_image),
        },
    ]


def build_editing_judge_content(case: TestCase, output_image: Path) -> list[dict]:
    assert case.image_inputs is not None and case.image_inputs.image_paths
    content: list[dict] = [
        {
            "type": "input_text",
            "text": f"Edit instruction:\n{case.prompt}\n\nCriteria:\n{case.criteria}",
        }
    ]
    for image_path in case.image_inputs.image_paths:
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(image_path),
            }
        )
    if case.image_inputs.mask_path:
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(case.image_inputs.mask_path),
            }
        )
    content.append(
        {
            "type": "input_image",
            "image_url": image_to_data_url(output_image),
        }
    )
    return content


def default_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["pass", "reason"],
        "additionalProperties": False,
    }


@dataclass
class LLMajRubricGrader:
    """
    Reusable vision LLM-as-judge grader.
    - Provide a system prompt + a content_builder for generation/editing.
    - Optionally provide a custom JSON schema and parser.
    """

    key: str
    system_prompt: str
    content_builder: Callable[[TestCase, Path], list[dict]]
    judge_model: str = "gpt-5.2"
    client: Optional[OpenAI] = None

    json_schema_name: str = "vision_eval_result"
    json_schema: dict = field(default_factory=default_schema)
    result_parser: Optional[Callable[[dict, str], Score | list[Score]]] = None

    def _parse_result(self, data: dict) -> Score | list[Score]:
        if self.result_parser:
            return self.result_parser(data, self.key)
        return Score(
            key=self.key,
            value=bool(data.get("pass", False)),
            reason=(data.get("reason") or "").strip(),
            tags=data.get("tags") or None,
        )

    def grade(self, response: ModelResponse, case: TestCase) -> Score | list[Score]:
        output_image = pick_first_image(response)
        if not output_image:
            return Score(key=self.key, value=False, reason="No output image artifact found")

        client = self.client or OpenAI()
        content = self.content_builder(case, output_image)

        completion = client.responses.create(
            model=self.judge_model,
            input=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": self.json_schema_name,
                    "schema": self.json_schema,
                    "strict": True,
                }
            },
        )

        data = json.loads(completion.output_text)
        return self._parse_result(data)
