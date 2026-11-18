"""Run with: python -m pytest examples/vector_databases/redis/tests"""

import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from examples.vector_databases.redis import nbutils


FILE_NAME = "vector_database_wikipedia_articles_embedded"
CSV_CONTENT = "id,title\n1,Example\n"


def create_archive(directory):
    archive_path = directory / f"{FILE_NAME}.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{FILE_NAME}.csv", CSV_CONTENT)
    return archive_path


@pytest.mark.parametrize("download_path", [".", "downloads"])
@pytest.mark.parametrize("cached", [True, False])
def test_download_removes_extracted_archive(
    tmp_path, monkeypatch, download_path, cached
):
    monkeypatch.chdir(tmp_path)
    download_directory = Path(download_path)
    download_directory.mkdir(exist_ok=True)
    archive_path = download_directory / f"{FILE_NAME}.zip"
    if cached:
        create_archive(download_directory)

    download = Mock(side_effect=lambda url, out: str(create_archive(Path(out))))
    monkeypatch.setattr(nbutils.wget, "download", download)

    nbutils.download_wikipedia_data(data_path="data", download_path=download_path)

    assert (tmp_path / "data" / f"{FILE_NAME}.csv").read_text() == CSV_CONTENT
    assert not archive_path.exists()
    assert download.call_count == (0 if cached else 1)


def test_download_preserves_same_named_file_in_working_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    download_directory = tmp_path / "downloads"
    download_directory.mkdir()
    archive_path = create_archive(download_directory)
    unrelated_file = tmp_path / f"{FILE_NAME}.zip"
    unrelated_file.write_bytes(b"unrelated user file")
    download = Mock()
    monkeypatch.setattr(nbutils.wget, "download", download)

    nbutils.download_wikipedia_data(data_path="data", download_path="downloads")

    assert unrelated_file.read_bytes() == b"unrelated user file"
    assert not archive_path.exists()
    download.assert_not_called()
