"""
Validate the backend (backends/dawn/_api.py) against the C header.

When there are changes in webgpu.h that affect how the backend should be
written, this module:

* Verifies the flags against the header.
* Annotates the C function calls and struct instantiations in _api.py with
  the corresponding signature/fields from the header, and adds a FIXME
  comment for what does not exist (anymore).

Adapted from wgpu-py's wgpu_native_patcher.py.
"""

import re
from collections import defaultdict
from itertools import chain

from codegen.utils import print, Patcher
from codegen.hparser import get_h_parser
from codegen.idlparser import get_idl_parser


def compare_flags():
    """For each flag in WebGPU:

    * Verify that there is a corresponding flag in webgpu.h
    * Verify that all fields are present too.
    * Verify that the (integer) value is equal.

    """

    idl = get_idl_parser()
    hp = get_h_parser()  # gets both headerfiles!

    name_map = {
        "ColorWrite": "ColorWriteMask",
    }

    for name, flag in idl.flags.items():
        name = name_map.get(name, name)
        if name not in hp.flags:
            print(f"Flag {name} missing in webgpu.h")
        else:
            for key, val in flag.items():
                key = key.title().replace("_", "")  # MAP_READ -> MapRead
                key = name_map.get(f"{name}.{key}") or key
                if key not in hp.flags[name]:
                    print(f"Flag field {name}.{key} missing in webgpu.h")
                elif val != hp.flags[name][key]:
                    print(f"Warning: Flag field {name}.{key} have different values.")


def patch_backend(code):
    """Given the Python code, applies patches to annotate functions
    calls and struct instantiations.

    For functions:

    * Verify that the function exists in webgpu.h. If not, add a fixme comment.
    * Add a comment showing corresponding signature from webgpu.h.

    For structs:

    * Verify that the struct name exists.
    * Verify that the correct form (pointer or not) is used.
    * Verify that all used fields exists.
    * Annotate any missing fields.
    * Add a comment that shows all fields and their type.

    """

    for patcher in [CommentRemover(), FunctionPatcher(), StructPatcher()]:
        patcher.apply(code)
        code = patcher.dumps()
    return code


class CommentRemover(Patcher):
    triggers = "# FIXME: unknown C", "# FIXME: invalid C", "# H:"

    def apply(self, code):
        self._init(code)
        for line, i in self.iter_lines():
            if line.lstrip().startswith(self.triggers):
                self.remove_line(i)


class FunctionPatcher(Patcher):
    def apply(self, code):
        self._init(code)
        hp = get_h_parser()
        count = 0
        detected = set()
        generic_class_var_assignment = defaultdict(list)
        generic_class_var_use = {}

        for line, i in self.iter_lines():
            if match := re.search(r"libf?\.(wgpu\w*)\(", line):
                # standard function call
                var_name = match.group(1)
                indent = " " * (len(line) - len(line.lstrip()))
                if "lib.wgpu" in line:
                    self.insert_line(
                        i, f"{indent}# FIXME: wgpu func calls must be done from libf"
                    )
                if var_name not in hp.functions:
                    msg = f"unknown C function {var_name}"
                    self.insert_line(i, f"{indent}# FIXME: {msg}")
                    print(f"ERROR: {msg}")
                else:
                    detected.add(var_name)
                    anno = hp.functions[var_name].replace(var_name, "f").strip(";")
                    self.insert_line(i, indent + "# H: " + anno)
                    count += 1
            elif match := re.search(r"(_\w+_function) = libf?\.(wgpu\w*)", line):
                # Assignment of libf function to a class variable. We'll point the
                # annotation at the point of use.
                var_name, lib_name = match.group(1, 2)
                if lib_name not in hp.functions:
                    msg = f"unknown C function {lib_name}"
                    indent = " " * (len(line) - len(line.lstrip()))
                    self.insert_line(i, f"{indent}# FIXME: {msg}")
                    print(f"ERROR: {msg}")
                else:
                    generic_class_var_assignment[var_name].append(lib_name)
            elif match := re.search(r"type\(self\).(_\w+_function)", line):
                # Calling the class variable. Keep track of where we are, so we can
                # patch in the appropriate annotations.
                var_name = match.group(1)
                generic_class_var_use[var_name] = (line, i)

        for var_name, (line, i) in generic_class_var_use.items():
            indent = " " * (len(line) - len(line.lstrip()))
            lib_names = generic_class_var_assignment.pop(var_name, ())
            if not lib_names:
                msg = f"There are no assignments to class field {var_name}"
                self.insert_line(i, f"{indent}# FIXME: {msg}")
                print(f"ERROR: {msg}")
            detected.update(lib_names)
            count += len(lib_names)
            for lib_name in lib_names:
                self.insert_line(
                    i, indent + "# H: " + hp.functions[lib_name].strip(";")
                )
        # At this point, generic_class_var_assignment should be empty.
        # If it is not, we've done an assignment to a class variable name, but have
        # never used it.
        for var_name, lib_names in generic_class_var_assignment.items():
            print(f"ERROR: {var_name} assigned a value but it is never used")

        print(f"Validated {count} C function calls")

        # Determine what functions were not detected
        # There are still quite a few, so we don't list them yet
        ignore = (
            "wgpu_create_surface_from",
            "wgpu_set_log_level",
            "wgpu_get_version",
            "wgpu_set_log_callback",
        )
        unused = set(name for name in hp.functions if not name.startswith(ignore))
        unused.difference_update(detected)
        print(f"Not using {len(unused)} C functions")


class StructPatcher(Patcher):
    def apply(self, code):
        self._init(code)
        count = 0

        for line, i in self.iter_lines():
            # detect struct definition start (only when not already inside a struct)
            if "new_struct_p(" in line or "new_struct(" in line:
                if line.lstrip().startswith("def "):
                    continue  # Implementation
                if "_new_struct" in line:
                    continue  # Implementation
                if "new_struct_p()" in line or "new_struct()" in line:
                    continue  # Comments or docs
                j = line.index("new_struct")
                line = line[j:]  # start brace searching from right pos
                # call a function to find the end and validate so we don't skip over nested structure in this loop
                self._find_struct_end(line, i)
                count += 1

        print(f"Validated {count} C structs")

    def _find_struct_end(self, first_line, start_line_index):
        """
        If a struct start is found, this function will find the end of the struct and then validate it
        """
        brace_depth = 0
        hp = get_h_parser()
        for line, i in chain(
            [(first_line, 0)], self.iter_lines(start_line=start_line_index + 1)
        ):
            for c in line:
                if c == "#":
                    break
                elif c == "(":
                    brace_depth += 1
                elif c == ")":
                    brace_depth -= 1
                    assert brace_depth >= 0
                    if brace_depth == 0:
                        # here we have found the end of this struct so now we can validate it.
                        self._validate_struct(hp, start_line_index, i)
                        return  # we assume it always works?

    def _validate_struct(self, hp, i1, i2):
        """Validate a specific struct usage."""

        lines = self.lines[
            i1 : i2 + 1
        ]  # note: i2 is the line index where the closing brace is
        indent = " " * (len(lines[-1]) - len(lines[-1].lstrip()))

        if len(lines) == 1:
            # Single line - add a comma before the closing brace
            print(
                "Notice: made a struct multiline. Rerun codegen to validate the struct."
            )
            line = lines[0]
            i = line.rindex(")")
            line = line[:i] + "," + line[i:]
            self.replace_line(i1, line)
            return
        elif len(lines) == 3 and lines[1].count("="):
            # Triplet - add a comma after the last element
            print(
                "Notice: made a struct multiline. Rerun codegen to validate the struct."
            )
            self.replace_line(i1 + 1, self.lines[i1 + 1] + ",")
            return

        # We can assume that the struct is multi-line and formatted
        assert len(lines) >= 3

        # Get struct name, and verify
        name = lines[1].strip().strip(',"')
        struct_name = name.strip(" *")
        if name.endswith("*"):
            if "new_struct_p" not in lines[0]:
                self.insert_line(
                    i1, indent + "# FIXME: invalid C struct, use new_struct_p()"
                )
        else:
            if "new_struct_p" in lines[0]:
                self.insert_line(
                    i1, indent + "# FIXME: invalid C struct, use new_struct()"
                )

        # Get struct object and create annotation line
        if struct_name not in hp.structs:
            msg = f"unknown C struct {struct_name}"
            self.insert_line(i1, f"{indent}# FIXME: {msg}")
            print(f"ERROR: {msg}")
            return
        else:
            struct = hp.structs[struct_name]
            fields = ", ".join(f"{key}: {val}" for key, val in struct.items())
            self.insert_line(i1, indent + "# H: " + fields)

        # Check keys
        brace_count = 0
        keys_found = []
        for j in range(2, len(lines) - 1):
            line = lines[j]
            if brace_count <= 0:
                # ready to find a new key candidate
                key = line.split("=")[0].strip()
                if key.startswith("# not used:"):
                    key = key.split(":")[1].split("=")[0].strip()
                elif key.startswith("#"):
                    continue
            # (still) inside a multi-line structure
            for c in line.strip():
                if c == "#":
                    break  # we can ignore this line past the comment in terms of nested structures
                elif c == "(":
                    brace_count += 1
                elif c == ")":
                    brace_count -= 1
            if brace_count == 0:
                # here we finished through the multi line structure
                keys_found.append(key)
                if key not in struct:
                    msg = f"unknown C struct field {struct_name}.{key}"
                    self.insert_line(i1 + j, f"{indent}# FIXME: {msg}")
                    print(f"ERROR: {msg}")

        # Insert comments for unused keys
        more_lines = []
        for key in struct:
            if key not in keys_found:
                more_lines.append(indent + f"    # not used: {key}")
        if more_lines:
            self.insert_line(i2, "\n".join(more_lines))
