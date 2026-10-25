"""Without a GPU adapter (e.g. a build machine without a Vulkan driver), a
test that needs one is skipped instead of failing: many tests (also those
from wgpu-py) request an adapter without checking for one first.
"""

import pytest

from testutils import can_use_wgpu_lib


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if can_use_wgpu_lib or call.excinfo is None or not report.failed:
        return
    error = call.excinfo.value
    if isinstance(error, RuntimeError) and "Request adapter failed" in str(error):
        report.outcome = "skipped"
        report.longrepr = (str(item.path), item.location[1] or 0, "No GPU adapter")
