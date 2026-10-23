# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "openai>=3.13.0",
#     "fastapi",
#     "psycopg[binary]",
#     "python-dotenv",
#     "uvicorn",
# ]
# ///

"""Serve the data analyst UI or run a single question."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

# Support direct execution from any working directory.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


from examples.agents_api.apps.data_analyst.agent import DataAnalyst
from examples.agents_api.apps.data_analyst.warehouse import Warehouse

EXAMPLE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncOpenAI() as client:
        app.state.analyst = DataAnalyst(client, Warehouse())
        try:
            yield
        finally:
            await app.state.analyst.close()


app = FastAPI(title="Data agent", lifespan=lifespan)


class Question(BaseModel):
    question: str
    conversation_id: str | None = None


class Memory(BaseModel):
    note: str
    scope: str = "personal"


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return (EXAMPLE_DIR / "index.html").read_text()


@app.get("/api/warehouse")
async def warehouse_summary() -> dict[str, Any]:
    analyst: DataAnalyst = app.state.analyst
    return analyst.warehouse.summary()


@app.get("/api/memories")
async def list_memories() -> dict[str, Any]:
    analyst: DataAnalyst = app.state.analyst
    return {"memories": analyst.warehouse.memory.list()}


@app.post("/api/memories")
async def create_memory(memory: Memory) -> dict[str, Any]:
    analyst: DataAnalyst = app.state.analyst
    try:
        return analyst.warehouse.memory.save(
            {"note": memory.note, "scope": memory.scope}
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, Any]:
    analyst: DataAnalyst = app.state.analyst
    try:
        analyst.warehouse.memory.delete(memory_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"memories": analyst.warehouse.memory.list()}


@app.post("/api/ask")
async def ask(question: Question) -> dict[str, Any]:
    analyst: DataAnalyst = app.state.analyst
    try:
        return await analyst.answer(question.question, question.conversation_id)
    except (PermissionError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def run_prompt(prompt: str) -> None:
    async with AsyncOpenAI() as client:
        analyst = DataAnalyst(client, Warehouse())
        try:
            result = await analyst.answer(prompt)
            print(result["answer"])
            queries = cast(list[str], result["queries"])
            if queries:
                print("\nVerified SQL:")
                for query in queries:
                    print(query)
        finally:
            await analyst.close()


def main() -> None:
    load_dotenv(EXAMPLE_DIR / ".env")
    parser = argparse.ArgumentParser(
        description="Ask questions about a read-only data warehouse."
    )
    parser.add_argument(
        "--prompt", metavar="QUESTION", help="Run one warehouse investigation."
    )
    args = parser.parse_args()

    if args.prompt:
        asyncio.run(run_prompt(args.prompt))
        return

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
