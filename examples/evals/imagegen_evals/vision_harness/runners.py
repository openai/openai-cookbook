from __future__ import annotations

import base64
from contextlib import ExitStack
from typing import Optional

from openai import OpenAI

from .storage import OutputStore
from .types import Artifact, ModelResponse, ModelRun, TestCase


def _mime_for_path(path) -> str:
    suffix = str(path).lower()
    if suffix.endswith(".png"):
        return "image/png"
    if suffix.endswith(".jpg") or suffix.endswith(".jpeg"):
        return "image/jpeg"
    if suffix.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _extract_b64_items(images_response) -> list[str]:
    b64_items: list[str] = []
    for item in getattr(images_response, "data", []) or []:
        b64 = getattr(item, "b64_json", None)
        if b64:
            b64_items.append(b64)
    return b64_items


class ImageGenerationRunner:
    """Text-to-image runner."""

    def __init__(self, client: Optional[OpenAI] = None):
        self.client = client or OpenAI()

    def run(self, case: TestCase, run_cfg: ModelRun, store: OutputStore) -> ModelResponse:
        assert case.task_type == "image_generation"
        assert run_cfg.task_type == "image_generation"

        params = dict(run_cfg.params)
        model = params.pop("model")
        n = int(params.pop("n", 1))

        run_dir = store.run_dir(case.id, run_cfg.label)
        basename = store.new_basename(f"gen_{case.id}_{run_cfg.label}")

        images_response = self.client.images.generate(
            model=model,
            prompt=case.prompt,
            n=n,
            **params,
        )

        artifacts: list[Artifact] = []
        for idx, b64_json in enumerate(_extract_b64_items(images_response)):
            png_bytes = base64.b64decode(b64_json)
            out_path = store.save_png(run_dir, basename, idx, png_bytes)
            artifacts.append(Artifact(kind="image", path=out_path))

        return ModelResponse(artifacts=artifacts, raw={"model": model, "params": run_cfg.params})


class ImageEditRunner:
    """Image editing runner (reference image(s) + optional mask)."""

    def __init__(self, client: Optional[OpenAI] = None):
        self.client = client or OpenAI()

    def run(self, case: TestCase, run_cfg: ModelRun, store: OutputStore) -> ModelResponse:
        assert case.task_type == "image_editing"
        assert run_cfg.task_type == "image_editing"
        assert case.image_inputs is not None and case.image_inputs.image_paths

        params = dict(run_cfg.params)
        model = params.pop("model")
        n = int(params.pop("n", 1))

        run_dir = store.run_dir(case.id, run_cfg.label)
        basename = store.new_basename(f"edit_{case.id}_{run_cfg.label}")

        with ExitStack() as stack:
            image_files = []
            for p in case.image_inputs.image_paths:
                f = stack.enter_context(p.open("rb"))
                image_files.append((p.name, f, _mime_for_path(p)))

            mask_file = None
            if case.image_inputs.mask_path:
                mf = stack.enter_context(case.image_inputs.mask_path.open("rb"))
                mask_file = (case.image_inputs.mask_path.name, mf, _mime_for_path(case.image_inputs.mask_path))

            edit_kwargs = dict(
                model=model,
                prompt=case.prompt,
                image=image_files,
                n=n,
                **params,
            )
            if mask_file is not None:
                edit_kwargs["mask"] = mask_file

            images_response = self.client.images.edit(**edit_kwargs)

        artifacts: list[Artifact] = []
        for idx, b64_json in enumerate(_extract_b64_items(images_response)):
            png_bytes = base64.b64decode(b64_json)
            out_path = store.save_png(run_dir, basename, idx, png_bytes)
            artifacts.append(Artifact(kind="image", path=out_path))

        return ModelResponse(artifacts=artifacts, raw={"model": model, "params": run_cfg.params})
