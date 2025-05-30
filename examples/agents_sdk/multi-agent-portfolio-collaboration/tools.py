# ---------------------------------------------------------------------------
# Standard library imports
# ---------------------------------------------------------------------------

import os
import json
from pathlib import Path
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
import re

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------

import pandas as pd  # pandas is a required dependency
import requests
from fredapi import Fred
from openai import OpenAI

# ---------------------------------------------------------------------------
# Local package imports
# ---------------------------------------------------------------------------

from agents import function_tool
from utils import outputs_dir, output_file

# ---------------------------------------------------------------------------
# Repository paths & globals
# ---------------------------------------------------------------------------

OUTPUT_DIR = outputs_dir()
PROMPT_PATH = Path(__file__).parent / "prompts" / "code_interpreter.md"
with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    CODE_INTERPRETER_INSTRUCTIONS = f.read()

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def code_interpreter_error_handler(ctx, error):
    """
    Custom error handler for run_code_interpreter. Returns a clear message to the LLM about what went wrong and how to fix it.
    """
    return (
        "Error running code interpreter. "
        "You must provide BOTH a clear natural language analysis request and a non-empty list of input_files (relative to outputs/). "
        f"Details: {str(error)}"
    )

@function_tool(failure_error_function=code_interpreter_error_handler)
def run_code_interpreter(request: str, input_files: list[str]) -> str:
    """
    Executes a quantitative analysis request using OpenAI's Code Interpreter (cloud).

    Args:
        request (str): A clear, quantitative analysis request describing the specific computation, statistical analysis, or visualization to perform on the provided data. 
            Examples:
                - "Calculate the Sharpe ratio for the portfolio returns in returns.csv."
                - "Plot a histogram of daily returns from the file 'AAPL_returns.csv'."
                - "Perform a linear regression of 'y' on 'x' in data.csv and report the R^2."
                - "Summarize the volatility of each ticker in the provided CSV."
        input_files (list[str]): A non-empty list of file paths (relative to outputs/) required for the analysis. Each file should contain the data needed for the requested quantitative analysis.
            Example: ["returns.csv", "tickers.csv"]

    Returns:
        str: JSON string with the analysis summary and a list of generated files (e.g., plots, CSVs) available for download.
    """
    # Input validation
    if not request or not isinstance(request, str):
        raise ValueError("The 'request' argument must be a non-empty string describing the analysis to perform.")
    if not input_files or not isinstance(input_files, list) or not all(isinstance(f, str) for f in input_files):
        raise ValueError("'input_files' must be a non-empty list of file paths (strings) relative to outputs/.")

    client = OpenAI()
    file_ids = []
    for file_path in input_files:
        abs_path = output_file(file_path, make_parents=False)
        if not abs_path.exists():
            raise ValueError(
                f"File not found: {file_path}. "
                "Use the list_output_files tool to see which files exist, "
                "and the read_file tool to see the contents of CSV files."
            )
        with abs_path.open("rb") as f:
            uploaded = client.files.create(file=f, purpose="user_data")
            file_ids.append(uploaded.id)

    instructions = CODE_INTERPRETER_INSTRUCTIONS

    resp = client.responses.create(
        model="gpt-4.1",
        tools=[
            {
                "type": "code_interpreter",
                "container": {"type": "auto", "file_ids": file_ids}
            }
        ],
        instructions=instructions,
        input=request,
        temperature=0,
    )

    output_text = resp.output_text
    # Extract container_id
    raw = resp.model_dump() if hasattr(resp, 'model_dump') else resp.__dict__
    container_id = None
    if "output" in raw:
        for item in raw["output"]:
            if item.get("type") == "code_interpreter_call" and "container_id" in item:
                container_id = item["container_id"]

    # Download any new files
    downloaded_files = []
    if container_id:
        api_key = os.environ["OPENAI_API_KEY"]
        url = f"https://api.openai.com/v1/containers/{container_id}/files"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp_files = requests.get(url, headers=headers)
        resp_files.raise_for_status()
        files = resp_files.json().get("data", [])
        for f in files:
            # Only download files not from user (i.e., generated)
            if f["source"] != "user":
                filename = f.get("path", "").split("/")[-1]
                cfile_id = f["id"]
                url_download = f"https://api.openai.com/v1/containers/{container_id}/files/{cfile_id}/content"
                resp_download = requests.get(url_download, headers=headers)
                resp_download.raise_for_status()
                out_path = output_file(filename)
                with open(out_path, "wb") as out:
                    out.write(resp_download.content)
                downloaded_files.append(str(out_path))

    # If no files were downloaded, raise error with <reason> tag if present
    if not downloaded_files:
        match = re.search(r'<reason>(.*?)</reason>', output_text, re.DOTALL)
        if match:
            reason = match.group(1).strip()
            raise ValueError(reason)
        raise ValueError("No downloads were generated and no <reason> was provided. Please call the tool again, and ask for downloadable files.")

    return json.dumps({
        "analysis": output_text,
        "files": downloaded_files,
    })

@function_tool
def write_markdown(filename: str, content: str) -> str:
    """Write `content` to `outputs/filename` and return confirmation JSON."""
    if not filename.endswith(".md"):
        filename += ".md"
    path = output_file(filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return json.dumps({"file": filename})

@function_tool
def read_file(filename: str, n_rows: int = 10) -> str:
    """
    Read and preview the contents of a file from the outputs directory.

    Supports reading CSV, Markdown (.md), and plain text (.txt) files. For CSV files, returns a preview of the last `n_rows` as a Markdown table. For Markdown and text files, returns the full text content. For unsupported file types, returns an error message.

    Args:
        filename: The name of the file to read, relative to the outputs directory. Supported extensions: .csv, .md, .txt.
        n_rows: The number of rows to preview for CSV files (default: 10).

    Returns:
        str: A JSON string containing either:
            - For CSV: {"file": filename, "preview_markdown": "<markdown table>"}
            - For Markdown/Text: {"file": filename, "content": "<text content>"}
            - For errors: {"error": "<error message>", "file": filename}
    """
    path = output_file(filename, make_parents=False)
    if not path.exists():
        return json.dumps({"error": "file not found", "file": filename})

    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            df = pd.read_csv(path).tail(n_rows)
            table_md = df.to_markdown(index=False)
            return json.dumps({"file": filename, "preview_markdown": table_md})
        except Exception as e:
            return json.dumps({"error": str(e), "file": filename})
    elif suffix == ".md" or suffix == ".txt":
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return json.dumps({"file": filename, "content": content})
        except Exception as e:
            return json.dumps({"error": str(e), "file": filename})
    else:
        return json.dumps({"error": f"Unsupported file type: {suffix}", "file": filename})

@function_tool
def get_fred_series(series_id: str, start_date: str, end_date: str, download_csv: bool = False) -> str:
    """Fetches a FRED economic time-series and returns simple summary statistics.

    Parameters
    ----------
    series_id : str
        FRED series identifier, e.g. "GDP" or "UNRATE".
    start_date : str
        ISO date string (YYYY-MM-DD).
    end_date : str
        ISO date string (YYYY-MM-DD).

    Returns
    -------
    str
        JSON string with basic statistics (mean, latest value, etc.). Falls back to a
        placeholder if fredapi is not available or an error occurs.
    """
    # Treat empty strings as unspecified
    start_date = start_date or None  # type: ignore
    end_date = end_date or None  # type: ignore

    if Fred is None:
        return json.dumps({"error": "fredapi not installed. returning stub result", "series_id": series_id})

    try:
        fred_api_key = os.getenv("FRED_API_KEY")
        fred = Fred(api_key=fred_api_key)
        data = fred.get_series(series_id, observation_start=start_date, observation_end=end_date)
        if data is None or data.empty:
            return json.dumps({"error": "Series not found or empty", "series_id": series_id})

        summary = {
            "series_id": series_id,
            "observations": len(data),
            "start": str(data.index.min().date()),
            "end": str(data.index.max().date()),
            "latest": float(data.iloc[-1]),
            "mean": float(data.mean()),
        }

        # ------------------------------------------------------------------
        # Optional CSV download
        # ------------------------------------------------------------------
        if download_csv:
            # Reset index to turn the DatetimeIndex into a column for CSV output
            df = data.reset_index()
            df.columns = ["Date", series_id]  # Capital D to match Yahoo Finance

            # Build date_range string for filename (YYYYMMDD-YYYYMMDD).
            start_str = start_date if start_date else str(df["Date"].min().date())
            end_str = end_date if end_date else str(df["Date"].max().date())
            date_range = f"{start_str}_{end_str}".replace("-", "")
            file_name = f"{series_id}_{date_range}.csv"

            # Save under outputs/
            csv_path = output_file(file_name)
            df.to_csv(csv_path, index=False)

            # Add file metadata to summary
            summary["file"] = file_name
            summary["schema"] = ["Date", series_id]

        return json.dumps(summary)
    except Exception as e:
        return json.dumps({"error": str(e), "series_id": series_id})

@function_tool
def list_output_files(extension: str = None) -> str:
    """
    List all files in the outputs directory. Optionally filter by file extension (e.g., 'png', 'csv', 'md').
    Returns a JSON list of filenames.
    """
    out_dir = outputs_dir()
    if extension:
        files = [f.name for f in out_dir.glob(f'*.{extension}') if f.is_file()]
    else:
        files = [f.name for f in out_dir.iterdir() if f.is_file()]
    return json.dumps({"files": files})

# Public interface -----------------------------------------------------------

__all__ = [
    "run_code_interpreter",
    "write_markdown",
    "get_fred_series",
    "list_output_files",
    "read_file",
] 