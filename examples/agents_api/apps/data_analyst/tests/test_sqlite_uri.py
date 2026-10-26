"""Offline regression tests for SQLite database URI handling."""

import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from examples.agents_api.apps.data_analyst.warehouse import Warehouse

FILENAMES = [
    "sales.db",
    "sales 2026.db",
    "sales#2026.db",
    "sales%232026.db",
]
if os.name != "nt":
    FILENAMES.append("sales?2026.db")


class SQLiteURIRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="cookbook-uri-test-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()

        # The decoy "sales" reveals accidental filename truncation.
        for filename in ["sales", *FILENAMES]:
            with closing(sqlite3.connect(self.folder / filename)) as connection:
                connection.execute("CREATE TABLE marker (label TEXT NOT NULL)")
                connection.execute("INSERT INTO marker VALUES (?)", (filename,))
                connection.commit()

    def open_warehouse(self, filename: str) -> Warehouse:
        path = self.folder / filename
        # Encode the input independently of the file-URI conversion being tested.
        return Warehouse(
            url="sqlite:" + quote(str(path), safe="/"),
            context={},
            memory_path=self.folder / "memories.json",
        )

    def test_opens_requested_database(self) -> None:
        for filename in FILENAMES:
            with self.subTest(filename=filename):
                with closing(self.open_warehouse(filename)) as warehouse:
                    result = warehouse.query({"sql": "SELECT label FROM marker"})
                    self.assertEqual(result["rows"], [{"label": filename}])

    def test_connections_are_read_only(self) -> None:
        for filename in FILENAMES:
            with self.subTest(filename=filename):
                with closing(self.open_warehouse(filename)) as warehouse:
                    try:
                        with self.assertRaises(sqlite3.OperationalError) as caught:
                            warehouse.connection.execute(
                                "INSERT INTO marker VALUES (?)", ("write test",)
                            )
                        self.assertEqual(
                            caught.exception.sqlite_errorcode & 0xFF,
                            sqlite3.SQLITE_READONLY,
                        )
                    finally:
                        warehouse.connection.rollback()

    def test_missing_database_is_not_created(self) -> None:
        for filename in FILENAMES:
            with self.subTest(filename=filename):
                before = set(self.folder.iterdir())
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    with closing(self.open_warehouse("missing_" + filename)):
                        pass
                self.assertEqual(
                    caught.exception.sqlite_errorcode & 0xFF,
                    sqlite3.SQLITE_CANTOPEN,
                )
                self.assertEqual(set(self.folder.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
