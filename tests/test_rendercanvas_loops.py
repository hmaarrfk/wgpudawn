"""Test that the async API of wgpudawn works in the event loops of rendercanvas.

Since rendercanvas 3, ``loop.add_task()`` runs a task on rendercanvas' own
micro-framework (``rendercanvas.utils.asyncadapter``), also when the loop is
the asyncio or trio loop. A GPUPromise awaited in such a task, and the
``sleep`` and ``Event`` of ``wgpudawn._async``, must work there.
"""

import importlib

import numpy as np
import pytest

import wgpudawn as wgpu
from wgpudawn import _async

from testutils import run_tests, can_use_wgpu_lib


if not can_use_wgpu_lib:
    pytest.skip("Skipping tests that need the wgpu lib", allow_module_level=True)

# rendercanvas imports wgpu by name, so this only tests wgpudawn when `wgpu`
# is wgpudawn, i.e. when the test-only shim (tests/wgpu_shim) is installed.
try:
    import wgpu as _wgpu_by_name
except ImportError:
    _wgpu_by_name = None
if getattr(_wgpu_by_name, "GPUDevice", None) is not wgpu.GPUDevice:
    pytest.skip(
        "Needs tests/wgpu_shim (rendercanvas imports wgpu)", allow_module_level=True
    )

from rendercanvas import offscreen


@pytest.mark.parametrize("loop_name", ["raw", "asyncio", "trio"])
def test_promises_in_a_rendercanvas_task(loop_name):
    if loop_name == "trio":
        pytest.importorskip("trio")
    loop = importlib.import_module(f"rendercanvas.{loop_name}").loop
    canvas_class = offscreen.RenderCanvas
    canvas_class.select_loop(loop)
    try:
        # A loop stops (and cancels its tasks) when it has no canvases
        canvas = canvas_class(size=(32, 16))
        results = {}

        async def task():
            try:
                results["async_lib"] = _async.detect_current_async_lib()
                adapter = await wgpu.gpu.request_adapter_async()
                device = await adapter.request_device_async()

                data = np.arange(4, dtype=np.uint32)
                buffer = device.create_buffer(
                    size=data.nbytes,
                    usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
                )
                device.queue.write_buffer(buffer, 0, data)
                await device.queue.on_submitted_work_done_async()
                await buffer.map_async("READ")
                results["data"] = np.frombuffer(buffer.read_mapped(), np.uint32).copy()
                buffer.unmap()

                await _async.async_sleep(0.001)
                event = _async.AsyncEvent()
                event.set()
                await event.wait()

                # And a frame through the wgpu context of the canvas
                context = canvas.get_wgpu_context()
                context.configure(
                    device=device, format=context.get_preferred_format(adapter)
                )
                encoder = device.create_command_encoder()
                render_pass = encoder.begin_render_pass(
                    color_attachments=[
                        {
                            "view": context.get_current_texture().create_view(),
                            "load_op": "clear",
                            "store_op": "store",
                            "clear_value": (0, 1, 0, 1),
                        }
                    ]
                )
                render_pass.end()
                device.queue.submit([encoder.finish()])
                results["done"] = True
            except BaseException as err:
                results["error"] = err
            finally:
                canvas.close()

        loop.add_task(task)
        loop.run()
    finally:
        canvas_class.select_loop(offscreen.loop)

    if "error" in results:
        raise results["error"]
    assert results.get("done"), results
    assert results["async_lib"] == "rendercanvas.utils.asyncadapter"
    assert results["data"].tolist() == [0, 1, 2, 3]


if __name__ == "__main__":
    run_tests(globals())
