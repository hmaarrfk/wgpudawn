"""Tests for Dawn's native extras of the instance, adapters and devices
(toggles, backends, feature information, memory, Vulkan handles), and for
wgpu-py's extras that Dawn has (multi-draw-indirect, write_timestamp).

``set_instance_extras`` configures the process-wide instance, so the tests
that use it run in a subprocess.
"""

import ctypes
import subprocess
import sys
import textwrap

import pytest

import wgpudawn as wgpu
from wgpudawn.backends.dawn import extras

from testutils import can_use_wgpu_lib

pytestmark = pytest.mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")


def run_in_subprocess(code):
    """Run code in a new interpreter; it prints SKIP <reason> or OK."""
    preamble = "import wgpudawn as wgpu\nfrom wgpudawn.backends.dawn import extras\n"
    result = subprocess.run(
        [sys.executable, "-c", preamble + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout
    assert result.returncode == 0, out + result.stderr
    lines = out.strip().splitlines()
    if lines and lines[-1].startswith("SKIP"):
        pytest.skip(lines[-1][5:])
    assert lines and lines[-1] == "OK", out + result.stderr
    return lines


def test_all_toggles():
    toggles = extras.all_toggles()
    assert len(toggles) > 100
    assert toggles["allow_unsafe_apis"]["stage"] == "instance"
    assert toggles["use_dxc"]["stage"] == "adapter"
    assert toggles["skip_validation"]["stage"] == "device"
    assert all(t["description"] for t in toggles.values())


def test_feature_info():
    info = extras.feature_info("multi-draw-indirect")
    assert info["name"] == "multi-draw-indirect"
    assert info["experimental"] is True
    assert extras.feature_info("shader-f16")["experimental"] is False
    with pytest.raises(KeyError):
        extras.feature_info("not-a-feature")


def test_toggles_of_adapter_and_device():
    adapter = wgpu.gpu.request_adapter_sync()
    assert isinstance(extras.get_toggles(adapter), list)
    device = extras.request_device_sync(adapter, enable_toggles=["dump_shaders"])
    assert "dump_shaders" in extras.get_toggles(device)
    adapter = wgpu.gpu.request_adapter_sync()  # an adapter makes one device
    assert "dump_shaders" not in extras.get_toggles(adapter.request_device_sync())
    with pytest.raises(ValueError):
        extras.request_device_sync(adapter, enable_toggles=["not_a_toggle"])
    with pytest.raises(ValueError):  # an instance toggle
        extras.request_device_sync(adapter, enable_toggles=["allow_unsafe_apis"])
    with pytest.raises(NotImplementedError):
        extras.request_device_sync(adapter, "trace-dir")


def test_set_instance_extras_after_the_instance_exists():
    wgpu.gpu.request_adapter_sync()
    with pytest.raises(RuntimeError):
        extras.set_instance_extras()


def test_set_instance_extras():
    run_in_subprocess("""
        try:
            extras.set_instance_extras(gles3_minor_version="Version2")
        except ValueError:
            pass
        else:
            raise AssertionError("expected a ValueError")
        backend = "Metal" if __import__("sys").platform == "darwin" else "Vulkan"
        extras.set_instance_extras(
            backends=[backend],
            enable_toggles=["allow_unsafe_apis", "dump_shaders"],
            disable_toggles=["lazy_clear_resource_on_first_use"],
        )
        adapters = wgpu.gpu.enumerate_adapters_sync()
        assert adapters and all(a.info["backend_type"] == backend for a in adapters)
        adapter = wgpu.gpu.request_adapter_sync()
        assert adapter.info["backend_type"] == backend
        assert "allow_unsafe_apis" in extras.get_toggles(adapter)
        device = adapter.request_device_sync()
        toggles = extras.get_toggles(device)
        assert "dump_shaders" in toggles, toggles
        assert "lazy_clear_resource_on_first_use" not in toggles, toggles
        # Per device: added to those of the instance, and can undo them
        adapter = wgpu.gpu.request_adapter_sync()
        device = extras.request_device_sync(adapter, disable_toggles=["dump_shaders"])
        assert "dump_shaders" not in extras.get_toggles(device)
        print("OK")
    """)


def test_memory_usage():
    device = wgpu.utils.get_default_device()
    before = extras.get_memory_usage(device)
    assert set(before) >= {"total", "buffers", "textures", "allocator_allocated"}
    buffer = device.create_buffer(size=4 << 20, usage="STORAGE")
    after = extras.get_memory_usage(device)
    assert after["buffers"] >= before["buffers"] + (4 << 20)
    del buffer
    extras.perform_idle_tasks(device)
    assert isinstance(extras.reduce_memory_usage(device), bool)


def test_vulkan_handles():
    device = wgpu.utils.get_default_device()
    if device.adapter.info["backend_type"] != "Vulkan":
        with pytest.raises(RuntimeError):
            extras.get_vk_instance(device)
        pytest.skip("Not a Vulkan device")
    instance = extras.get_vk_instance(device)
    assert instance
    # Make a Vulkan call on Dawn's instance, as another library would
    address = extras.get_vk_instance_proc_addr(device, "vkEnumeratePhysicalDevices")
    assert address
    assert extras.get_vk_instance_proc_addr(device, "vkNotAFunction") == 0
    enumerate_devices = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    )(address)
    count = ctypes.c_uint32(0)
    assert enumerate_devices(instance, ctypes.byref(count), None) == 0  # VK_SUCCESS
    assert count.value >= 1


# %% wgpu-py's extras: multi-draw-indirect and write_timestamp

# Each draw puts one point at pixel x = first_instance of a 8x1 target
MULTI_DRAW = """
    import numpy as np
    extras.set_instance_extras(enable_toggles=["allow_unsafe_apis"])
    adapter = wgpu.gpu.request_adapter_sync()
    needed = ["multi-draw-indirect", "indirect-first-instance"]
    if not all(f in adapter.features for f in needed):
        print("SKIP adapter lacks", needed)
        raise SystemExit
    device = adapter.request_device_sync(required_features=needed)
    shader = device.create_shader_module(code='''
        @vertex fn vs(@builtin(instance_index) i: u32) -> @builtin(position) vec4f {
            return vec4f((f32(i) + 0.5) / 4.0 - 1.0, 0.0, 0.0, 1.0);
        }
        @fragment fn fs() -> @location(0) vec4f { return vec4f(1.0); }
    ''')
    pipeline = device.create_render_pipeline(
        layout="auto",
        vertex={"module": shader, "entry_point": "vs"},
        fragment={"module": shader, "entry_point": "fs",
                  "targets": [{"format": "rgba8unorm"}]},
        primitive={"topology": "point-list"},
    )
    # draw: vertex_count, instance_count, first_vertex, first_instance
    # indexed: index_count, instance_count, first_index, base_vertex, first_instance
    draws = [1, 1, 0, 1, 1, 1, 0, 3, 1, 1, 0, 6]
    indexed = [1, 1, 0, 0, 1, 1, 1, 0, 0, 3, 1, 1, 0, 0, 6]
    usage = wgpu.BufferUsage.INDIRECT | wgpu.BufferUsage.COPY_DST
    def buffer(data, usage=usage):
        return device.create_buffer_with_data(data=np.array(data, np.uint32), usage=usage)
    index_buffer = buffer([0, 0], wgpu.BufferUsage.INDEX)

    def render(call, **kwargs):
        texture = device.create_texture(
            size=(8, 1, 1), format="rgba8unorm",
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        encoder = device.create_command_encoder()
        rpass = encoder.begin_render_pass(color_attachments=[{
            "view": texture.create_view(), "load_op": "clear", "store_op": "store",
            "clear_value": (0, 0, 0, 0)}])
        rpass.set_pipeline(pipeline)
        rpass.set_index_buffer(index_buffer, "uint32")
        call(rpass, **kwargs)
        rpass.end()
        device.queue.submit([encoder.finish()])
        data = device.queue.read_texture(
            {"texture": texture}, {"bytes_per_row": 256}, (8, 1, 1))
        return [x for x in range(8) if np.frombuffer(data, np.uint8)[4 * x] == 255]

    assert render(extras.multi_draw_indirect, buffer=buffer(draws), count=3) == [1, 3, 6]
    assert render(extras.multi_draw_indirect, buffer=buffer(draws), offset=16, count=2) == [3, 6]
    assert render(extras.multi_draw_indexed_indirect, buffer=buffer(indexed), count=3) == [1, 3, 6]
    count = buffer([2, 99])
    assert render(extras.multi_draw_indirect_count, buffer=buffer(draws),
                  count_buffer=count, max_count=3) == [1, 3]
    assert render(extras.multi_draw_indexed_indirect_count, buffer=buffer(indexed),
                  count_buffer=count, count_buffer_offset=4, max_count=2) == [1, 3]
    print("OK")
"""


def test_multi_draw_indirect():
    run_in_subprocess(MULTI_DRAW)


WRITE_TIMESTAMP = """
    import numpy as np
    extras.set_instance_extras(enable_toggles=["allow_unsafe_apis"])
    adapter = wgpu.gpu.request_adapter_sync()
    if "timestamp-query" not in adapter.features:
        print("SKIP adapter lacks timestamp-query")
        raise SystemExit
    features = ["timestamp-query"]
    in_passes = "chromium-experimental-timestamp-query-inside-passes"
    if in_passes in adapter.features:
        features.append(in_passes)
    device = adapter.request_device_sync(required_features=features)
    query_set = device.create_query_set(type="timestamp", count=4)
    buffer = device.create_buffer(
        size=32, usage=wgpu.BufferUsage.QUERY_RESOLVE | wgpu.BufferUsage.COPY_SRC
    )
    encoder = device.create_command_encoder()
    extras.write_timestamp(encoder, query_set, 0)
    encoder.clear_buffer(device.create_buffer(size=1 << 20, usage="COPY_DST"))
    extras.write_timestamp(encoder, query_set, 1)
    if in_passes in features:
        cpass = encoder.begin_compute_pass()
        extras.write_timestamp(cpass, query_set, 2)
        extras.write_timestamp(cpass, query_set, 3)
        cpass.end()
    encoder.resolve_query_set(query_set, 0, 4, buffer, 0)
    device.queue.submit([encoder.finish()])
    t = np.frombuffer(device.queue.read_buffer(buffer), np.uint64)
    assert 0 < t[0] <= t[1], t
    if in_passes in features:
        assert t[1] <= t[2] <= t[3], t
    print("OK")
"""


def test_write_timestamp():
    run_in_subprocess(WRITE_TIMESTAMP)
