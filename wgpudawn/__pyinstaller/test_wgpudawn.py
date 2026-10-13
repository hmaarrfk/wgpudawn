script = """
# The script part
import sys
import importlib
import wgpudawn

# The test part
if "is_test" in sys.argv:
    included_modules = [
        "wgpudawn.backends.auto",
        "wgpudawn.backends.dawn",
    ]
    excluded_modules = [
        "PySide6",
        "PyQt6",
    ]
    for module_name in included_modules:
        importlib.import_module(module_name)
    for module_name in excluded_modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        raise RuntimeError(module_name + " is not supposed to be importable.")
"""


def test_pyi_wgpudawn(pyi_builder):
    pyi_builder.test_source(script, app_args=["is_test"])
