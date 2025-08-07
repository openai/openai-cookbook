from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    ADD = "add"
    DELETE = "delete"
    UPDATE = "update"


class FileChange(BaseModel):
    type: ActionType
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    move_path: Optional[str] = None


class Commit(BaseModel):
    changes: dict[str, FileChange] = Field(default_factory=dict)


def assemble_changes(orig: dict[str, Optional[str]], dest: dict[str, Optional[str]]) -> Commit:
    commit = Commit()
    for path in sorted(set(orig.keys()).union(dest.keys())):
        old_content = orig.get(path)
        new_content = dest.get(path)
        if old_content != new_content:
            if old_content is not None and new_content is not None:
                commit.changes[path] = FileChange(
                    type=ActionType.UPDATE,
                    old_content=old_content,
                    new_content=new_content,
                )
            elif new_content:
                commit.changes[path] = FileChange(
                    type=ActionType.ADD,
                    new_content=new_content,
                )
            elif old_content:
                commit.changes[path] = FileChange(
                    type=ActionType.DELETE,
                    old_content=old_content,
                )
            else:
                assert False
    return commit


from pydantic import BaseModel, Field


class Chunk(BaseModel):
    orig_index: int = -1  # line index of the first line in the original file
    del_lines: list[str] = Field(default_factory=list)
    ins_lines: list[str] = Field(default_factory=list)


class PatchAction(BaseModel):
    type: ActionType
    new_file: Optional[str] = None
    chunks: list[Chunk] = Field(default_factory=list)
    move_path: Optional[str] = None


class Patch(BaseModel):
    actions: dict[str, PatchAction] = Field(default_factory=dict)


from pydantic import BaseModel, Field


class Parser(BaseModel):
    current_files: dict[str, str] = Field(default_factory=dict)
    lines: list[str] = Field(default_factory=list)
    index: int = 0
    patch: Patch = Field(default_factory=Patch)
    fuzz: int = 0

    def is_done(self, prefixes: Optional[tuple[str, ...]] = None) -> bool:
        if self.index >= len(self.lines):
            return True
        if prefixes and self.lines[self.index].startswith(prefixes):
            return True
        return False

    def startswith(self, prefix: Optional[tuple[str, ...]]) -> bool:
        assert self.index < len(self.lines), f"Index: {self.index} >= {len(self.lines)}"
        if self.lines[self.index].startswith(prefix):
            return True
        return False

    def read_str(self, prefix: str = "", return_everything: bool = False) -> str:
        assert self.index < len(self.lines), f"Index: {self.index} >= {len(self.lines)}"
        if self.lines[self.index].startswith(prefix):
            if return_everything:
                text = self.lines[self.index]
            else:
                text = self.lines[self.index][len(prefix) :]
            self.index += 1
            return text
        return ""

    def parse(self):
        while not self.is_done(("*** End Patch",)):
            path = self.read_str("*** Update File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Update File Error: Duplicate Path: {path}")
                move_to = self.read_str("*** Move to: ")
                if path not in self.current_files:
                    raise DiffError(f"Update File Error: Missing File: {path}")
                text = self.current_files[path]
                action = self.parse_update_file(text)
                # TODO: Check move_to is valid
                action.move_path = move_to
                self.patch.actions[path] = action
                continue
            path = self.read_str("*** Delete File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Delete File Error: Duplicate Path: {path}")
                if path not in self.current_files:
                    raise DiffError(f"Delete File Error: Missing File: {path}")
                self.patch.actions[path] = PatchAction(
                    type=ActionType.DELETE,
                )
                continue
            path = self.read_str("*** Add File: ")
            if path:
                if path in self.patch.actions:
                    raise DiffError(f"Add File Error: Duplicate Path: {path}")
                self.patch.actions[path] = self.parse_add_file()
                continue
            raise DiffError(f"Unknown Line: {self.lines[self.index]}")
        if not self.startswith("*** End Patch"):
            raise DiffError("Missing End Patch")
        self.index += 1

    def parse_update_file(self, text: str) -> PatchAction:
        # self.lines / self.index refers to the patch
        # lines / index refers to the file being modified
        # print("parse update file")
        action = PatchAction(
            type=ActionType.UPDATE,
        )
        lines = text.split("\n")
        index = 0
        while not self.is_done(
            (
                "*** End Patch",
                "*** Update File:",
                "*** Delete File:",
                "*** Add File:",
                "*** End of File",
            )
        ):
            def_str = self.read_str("@@ ")
            section_str = ""
            if not def_str:
                if self.lines[self.index] == "@@":
                    section_str = self.lines[self.index]
                    self.index += 1
            if not (def_str or section_str or index == 0):
                raise DiffError(f"Invalid Line:\n{self.lines[self.index]}")
            if def_str.strip():
                found = False
                if not [s for s in lines[:index] if s == def_str]:
                    # def str is a skip ahead operator
                    for i, s in enumerate(lines[index:], index):
                        if s == def_str:
                            # print(f"Jump ahead @@: {index} -> {i}: {def_str}")
                            index = i + 1
                            found = True
                            break
                if not found and not [s for s in lines[:index] if s.strip() == def_str.strip()]:
                    # def str is a skip ahead operator
                    for i, s in enumerate(lines[index:], index):
                        if s.strip() == def_str.strip():
                            # print(f"Jump ahead @@: {index} -> {i}: {def_str}")
                            index = i + 1
                            self.fuzz += 1
                            found = True
                            break
            next_chunk_context, chunks, end_patch_index, eof = peek_next_section(
                self.lines, self.index
            )
            next_chunk_text = "\n".join(next_chunk_context)
            new_index, fuzz = find_context(lines, next_chunk_context, index, eof)
            if new_index == -1:
                if eof:
                    raise DiffError(f"Invalid EOF Context {index}:\n{next_chunk_text}")
                else:
                    raise DiffError(f"Invalid Context {index}:\n{next_chunk_text}")
            self.fuzz += fuzz
            # print(f"Jump ahead: {index} -> {new_index}")
            for ch in chunks:
                ch.orig_index += new_index
                action.chunks.append(ch)
            index = new_index + len(next_chunk_context)
            self.index = end_patch_index
            continue
        return action

    def parse_add_file(self) -> PatchAction:
        lines = []
        while not self.is_done(
            ("*** End Patch", "*** Update File:", "*** Delete File:", "*** Add File:")
        ):
            s = self.read_str()
            if not s.startswith("+"):
                raise DiffError(f"Invalid Add File Line: {s}")
            s = s[1:]
            lines.append(s)
        return PatchAction(
            type=ActionType.ADD,
            new_file="\n".join(lines),
        )


def find_context_core(lines: list[str], context: list[str], start: int) -> tuple[int, int]:
    if not context:
        print("context is empty")
        return start, 0

    # Prefer identical
    for i in range(start, len(lines)):
        if lines[i : i + len(context)] == context:
            return i, 0
    # RStrip is ok
    for i in range(start, len(lines)):
        if [s.rstrip() for s in lines[i : i + len(context)]] == [s.rstrip() for s in context]:
            return i, 1
    # Fine, Strip is ok too.
    for i in range(start, len(lines)):
        if [s.strip() for s in lines[i : i + len(context)]] == [s.strip() for s in context]:
            return i, 100
    return -1, 0


def find_context(lines: list[str], context: list[str], start: int, eof: bool) -> tuple[int, int]:
    if eof:
        new_index, fuzz = find_context_core(lines, context, len(lines) - len(context))
        if new_index != -1:
            return new_index, fuzz
        new_index, fuzz = find_context_core(lines, context, start)
        return new_index, fuzz + 10000
    return find_context_core(lines, context, start)


def peek_next_section(lines: list[str], index: int) -> tuple[list[str], list[Chunk], int, bool]:
    old: list[str] = []
    del_lines: list[str] = []
    ins_lines: list[str] = []
    chunks: list[Chunk] = []
    mode = "keep"
    orig_index = index
    while index < len(lines):
        s = lines[index]
        if s.startswith(
            (
                "@@",
                "*** End Patch",
                "*** Update File:",
                "*** Delete File:",
                "*** Add File:",
                "*** End of File",
            )
        ):
            break
        if s == "***":
            break
        elif s.startswith("***"):
            raise DiffError(f"Invalid Line: {s}")
        index += 1
        last_mode = mode
        if s == "":
            s = " "
        if s[0] == "+":
            mode = "add"
        elif s[0] == "-":
            mode = "delete"
        elif s[0] == " ":
            mode = "keep"
        else:
            raise DiffError(f"Invalid Line: {s}")
        s = s[1:]
        if mode == "keep" and last_mode != mode:
            if ins_lines or del_lines:
                chunks.append(
                    Chunk(
                        orig_index=len(old) - len(del_lines),
                        del_lines=del_lines,
                        ins_lines=ins_lines,
                    )
                )
            del_lines = []
            ins_lines = []
        if mode == "delete":
            del_lines.append(s)
            old.append(s)
        elif mode == "add":
            ins_lines.append(s)
        elif mode == "keep":
            old.append(s)
    if ins_lines or del_lines:
        chunks.append(
            Chunk(
                orig_index=len(old) - len(del_lines),
                del_lines=del_lines,
                ins_lines=ins_lines,
            )
        )
        del_lines = []
        ins_lines = []
    if index < len(lines) and lines[index] == "*** End of File":
        index += 1
        return old, chunks, index, True
    if index == orig_index:
        raise DiffError(f"Nothing in this section - {index=} {lines[index]}")
    return old, chunks, index, False


def text_to_patch(text: str, orig: dict[str, str]) -> tuple[Patch, int]:
    lines = text.strip().split("\n")
    if len(lines) < 2 or not lines[0].startswith("*** Begin Patch") or lines[-1] != "*** End Patch":
        raise DiffError("Invalid patch text")

    parser = Parser(
        current_files=orig,
        lines=lines,
        index=1,
    )
    parser.parse()
    return parser.patch, parser.fuzz


def identify_files_needed(text: str) -> list[str]:
    lines = text.strip().split("\n")
    result = set()
    for line in lines:
        if line.startswith("*** Update File: "):
            result.add(line[len("*** Update File: ") :])
        if line.startswith("*** Delete File: "):
            result.add(line[len("*** Delete File: ") :])
    return list(result)


def _get_updated_file(text: str, action: PatchAction, path: str) -> str:
    assert action.type == ActionType.UPDATE
    orig_lines = text.split("\n")
    dest_lines = []
    orig_index = 0
    dest_index = 0
    for chunk in action.chunks:
        # Process the unchanged lines before the chunk
        if chunk.orig_index > len(orig_lines):
            print(
                f"_get_updated_file: {path}: chunk.orig_index {chunk.orig_index} > len(lines) {len(orig_lines)}"
            )
            raise DiffError(
                f"_get_updated_file: {path}: chunk.orig_index {chunk.orig_index} > len(lines) {len(orig_lines)}"
            )
        if orig_index > chunk.orig_index:
            raise DiffError(
                f"_get_updated_file: {path}: orig_index {orig_index} > chunk.orig_index {chunk.orig_index}"
            )
        assert orig_index <= chunk.orig_index
        dest_lines.extend(orig_lines[orig_index : chunk.orig_index])
        delta = chunk.orig_index - orig_index
        orig_index += delta
        dest_index += delta
        # Process the inserted lines
        if chunk.ins_lines:
            for i in range(len(chunk.ins_lines)):
                dest_lines.append(chunk.ins_lines[i])
            dest_index += len(chunk.ins_lines)
        orig_index += len(chunk.del_lines)
    # Final part
    dest_lines.extend(orig_lines[orig_index:])
    delta = len(orig_lines) - orig_index
    orig_index += delta
    dest_index += delta
    assert orig_index == len(orig_lines)
    assert dest_index == len(dest_lines)
    return "\n".join(dest_lines)


def patch_to_commit(patch: Patch, orig: dict[str, str]) -> Commit:
    commit = Commit()
    for path, action in patch.actions.items():
        if action.type == ActionType.DELETE:
            commit.changes[path] = FileChange(type=ActionType.DELETE, old_content=orig[path])
        elif action.type == ActionType.ADD:
            commit.changes[path] = FileChange(type=ActionType.ADD, new_content=action.new_file)
        elif action.type == ActionType.UPDATE:
            new_content = _get_updated_file(text=orig[path], action=action, path=path)
            commit.changes[path] = FileChange(
                type=ActionType.UPDATE,
                old_content=orig[path],
                new_content=new_content,
                move_path=action.move_path,
            )
    return commit


class DiffError(ValueError):
    pass


import os
from typing import Callable


def load_files(paths: list[str], open_fn: Callable) -> dict[str, str]:
    orig = {}
    for path in paths:
        orig[path] = open_fn(path)
    return orig


def apply_commit(commit: Commit, write_fn: Callable, remove_fn: Callable) -> None:
    for path, change in commit.changes.items():
        if change.type == ActionType.DELETE:
            remove_fn(path)
        elif change.type == ActionType.ADD:
            write_fn(path, change.new_content)
        elif change.type == ActionType.UPDATE:
            if change.move_path:
                write_fn(change.move_path, change.new_content)
                remove_fn(path)
            else:
                write_fn(path, change.new_content)


def process_patch(text: str, open_fn: Callable, write_fn: Callable, remove_fn: Callable) -> str:
    assert text.startswith("*** Begin Patch")
    paths = identify_files_needed(text)
    orig = load_files(paths, open_fn)
    patch, fuzz = text_to_patch(text, orig)
    commit = patch_to_commit(patch, orig)
    apply_commit(commit, write_fn, remove_fn)
    return "Done!"


def open_file(path: str) -> str:
    with open(path, "rt") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    if path.startswith("/"):
        print("We do not support absolute paths.")
        return
    if "/" in path:
        parent = "/".join(path.split("/")[:-1])
        os.makedirs(parent, exist_ok=True)
    with open(path, "wt") as f:
        f.write(content)


def remove_file(path: str) -> None:
    os.remove(path)


def main():
    import sys

    patch_text = sys.stdin.read()
    if not patch_text:
        print("Please pass patch text through stdin")
        return
    try:
        result = process_patch(patch_text, open_file, write_file, remove_file)
    except DiffError as e:
        print(str(e))
        return
    print(result)


if __name__ == "__main__":
    main()