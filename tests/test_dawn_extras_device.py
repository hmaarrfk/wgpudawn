"""Tests for Dawn's native extras of the instance, adapters and devices
(toggles, backends, feature information, memory, Vulkan handles), and for
wgpu-py's extras that Dawn has (multi-draw-indirect, write_timestamp).

``set_instance_extras`` configures the process-wide instance, so the tests
that use it run in a subprocess.
"""

import ctypes
import os
import subprocess
import sys
import textwrap

import numpy as np
import pytest

import wgpudawn as wgpu
from wgpudawn.backends.dawn import extras

from testutils import can_use_wgpu_lib

pytestmark = pytest.mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")


def run_in_subprocess(code):
    """Run code in a new interpreter; it prints SKIP <reason> or OK."""
    preamble = "import wgpudawn as wgpu\nfrom wgpudawn.backends.dawn import extras\n"
    first, _, rest = code.partition("\n")
    if not first.strip():  # code that starts with a newline is indented
        code = textwrap.dedent(rest)
    else:  # a line of setup, then the indented code
        code = first + "\n" + textwrap.dedent(rest)
    result = subprocess.run(
        [sys.executable, "-c", preamble + code],
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
    # The backend of the default adapter (in a subprocess, before the instance)
    backend = wgpu.gpu.request_adapter_sync().info["backend_type"]
    run_in_subprocess(
        f"backend = {backend!r}\n"
        + """
        try:
            extras.set_instance_extras(gles3_minor_version="Version2")
        except ValueError:
            pass
        else:
            raise AssertionError("expected a ValueError")
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
    """
    )


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


# %% Adapter properties and format capabilities


def test_feature_names_of_the_extras_exist():
    # The extras ask adapters for features by name; a misspelt one is never
    # there, and its extra silently does nothing
    import re
    from wgpudawn.backends.dawn import _extras_adapter, _extras_memory
    from wgpudawn.backends.dawn._mappings import enum_str2int, enummap

    names = set(enum_str2int["FeatureName"])
    names |= {k.split(".", 1)[1] for k in enummap if k.startswith("FeatureName.")}
    for module in (extras, _extras_adapter, _extras_memory):
        source = open(module.__file__).read()
        for name in re.findall(r"``([a-z0-9-]+)``", source) + re.findall(
            r'"([a-z0-9]+(?:-[a-z0-9]+)+)" (?:in|not in) ', source
        ):
            if name.startswith(("shared-", "adapter-properties-", "dawn-")) or name in (
                "host-mapped-pointer",
                "chromium-experimental-subgroup-matrix",
            ):
                assert name in names, f"{module.__name__}: unknown feature {name}"


def test_adapter_properties():
    adapter = wgpu.gpu.request_adapter_sync()
    properties = extras.get_adapter_properties(adapter)
    features = adapter.features
    assert ("vk" in properties) == ("adapter-properties-vk" in features)
    assert ("d3d" in properties) == ("adapter-properties-d-3d" in features)
    if "adapter-properties-memory-heaps" in features:
        heaps = properties["memory_heaps"]
        assert heaps and all(h["size"] > 0 for h in heaps)
        assert any("device-local" in h["properties"] for h in heaps)
    if "d3d" in properties:
        assert properties["d3d"]["shader_model"] >= 50
        assert properties["d3d"]["luid"] != 0
    drm = properties.get("drm")
    if drm and drm["render"]:
        rdev = os.stat(drm["render_node"]).st_rdev
        assert (os.major(rdev), os.minor(rdev)) == drm["render"]


def test_vulkan_uuid_is_that_of_a_vulkan_device():
    # The device UUID of the adapter is the one Vulkan reports for the GPU
    # (which is how CUDA, OpenGL or another Vulkan program finds the same GPU)
    adapter = wgpu.gpu.request_adapter_sync()
    if adapter.info["backend_type"] != "Vulkan":
        pytest.skip("Not a Vulkan adapter")
    uuid = extras.get_adapter_properties(adapter)["vulkan_uuids"]["device_uuid"]
    assert len(uuid) == 16 and any(uuid)
    device = adapter.request_device_sync()
    instance = extras.get_vk_instance(device)

    def vk(name, restype, *argtypes):
        address = extras.get_vk_instance_proc_addr(device, name)
        assert address, name
        return ctypes.CFUNCTYPE(restype, *argtypes)(address)

    enumerate_devices = vk(
        "vkEnumeratePhysicalDevices",
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_properties2 = vk(
        "vkGetPhysicalDeviceProperties2", None, ctypes.c_void_p, ctypes.c_void_p
    )

    class IDProperties(ctypes.Structure):
        _fields_ = [
            ("sType", ctypes.c_int32),
            ("pNext", ctypes.c_void_p),
            ("deviceUUID", ctypes.c_uint8 * 16),
            ("driverUUID", ctypes.c_uint8 * 16),
            ("deviceLUID", ctypes.c_uint8 * 8),
            ("deviceNodeMask", ctypes.c_uint32),
            ("deviceLUIDValid", ctypes.c_uint32),
        ]

    class Properties2(ctypes.Structure):
        _fields_ = [
            ("sType", ctypes.c_int32),
            ("pNext", ctypes.c_void_p),
            ("properties", ctypes.c_uint8 * 2048),  # VkPhysicalDeviceProperties
        ]

    count = ctypes.c_uint32(0)
    assert enumerate_devices(instance, ctypes.byref(count), None) == 0
    physical = (ctypes.c_void_p * count.value)()
    assert enumerate_devices(instance, ctypes.byref(count), physical) == 0
    uuids = []
    for handle in physical:
        ids = IDProperties(sType=1000071004)  # PHYSICAL_DEVICE_ID_PROPERTIES
        props = Properties2(sType=1000059001, pNext=ctypes.addressof(ids))
        get_properties2(handle, ctypes.byref(props))
        uuids.append(bytes(ids.deviceUUID))
    assert uuid in uuids


def test_format_capabilities():
    adapter = wgpu.gpu.request_adapter_sync()
    with pytest.raises(KeyError):
        extras.get_format_capabilities(adapter, "not-a-format")
    if "dawn-drm-format-capabilities" not in adapter.features:
        with pytest.raises(RuntimeError):
            extras.get_format_capabilities(adapter, "bgra8unorm")
        pytest.skip("Adapter lacks dawn-drm-format-capabilities")
    modifiers = extras.get_format_capabilities(adapter, "bgra8unorm")["drm_modifiers"]
    assert modifiers and all(m["plane_count"] >= 1 for m in modifiers)
    assert any(m["modifier"] == 0 for m in modifiers)  # DRM_FORMAT_MOD_LINEAR


# %% Host memory


HOST_MEMORY = """
    import gc
    import numpy as np
    from wgpudawn.backends.dawn._ffi import callbacks

    extras.set_instance_extras(enable_toggles=["allow_unsafe_apis"])
    adapter = wgpu.gpu.request_adapter_sync()
    if "host-mapped-pointer" not in adapter.features:
        print("SKIP adapter lacks host-mapped-pointer")
        raise SystemExit
    device = adapter.request_device_sync(required_features=["host-mapped-pointer"])
    alignment = extras.get_host_memory_alignment(device)
    assert alignment > 0 and alignment & (alignment - 1) == 0

    memory = extras.allocate_host_memory(device, 1000)
    assert memory.nbytes % alignment == 0 and not memory.readonly
    try:
        extras.create_buffer_from_host_memory(device, memory[1:], usage="STORAGE")
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for unaligned memory")

    # The GPU works on the memory itself: a compute shader doubles the array
    array = np.frombuffer(memory, np.float32)
    array[:] = np.arange(array.size)
    pending = len(callbacks._callbacks)
    buffer = extras.create_buffer_from_host_memory(device, array, usage="STORAGE")
    assert buffer.size == memory.nbytes
    shader = device.create_shader_module(code='''
        @group(0) @binding(0) var<storage, read_write> x: array<f32>;
        @compute @workgroup_size(64) fn main(@builtin(global_invocation_id) i: vec3u) {
            if (i.x < arrayLength(&x)) { x[i.x] = x[i.x] * 2.0; }
        }
    ''')
    pipeline = device.create_compute_pipeline(
        layout="auto", compute={"module": shader, "entry_point": "main"})
    bind_group = device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[{"binding": 0, "resource": {"buffer": buffer}}])
    encoder = device.create_command_encoder()
    cpass = encoder.begin_compute_pass()
    cpass.set_pipeline(pipeline)
    cpass.set_bind_group(0, bind_group)
    cpass.dispatch_workgroups(array.size // 64 + 1)
    cpass.end()
    device.queue.submit([encoder.finish()])
    device.queue.on_submitted_work_done_sync()
    assert np.array_equal(array, np.arange(array.size) * 2), array[:8]

    # Dawn lets go of the memory after the buffer is destroyed and later work
    # is done, when it processes events
    assert len(callbacks._callbacks) == pending + 1
    buffer.destroy()
    del buffer, bind_group
    gc.collect()
    other = device.create_buffer(size=256, usage="COPY_DST")
    for i in range(5):
        encoder = device.create_command_encoder()
        encoder.clear_buffer(other)
        device.queue.submit([encoder.finish()])
        device.queue.on_submitted_work_done_sync()
        extras.process_events()
        if len(callbacks._callbacks) == pending:
            break
    assert len(callbacks._callbacks) == pending, "the memory was not released"
    print("OK")
"""


def test_host_memory():
    run_in_subprocess(HOST_MEMORY)


# %% Video: multi-planar formats and external textures


def test_yuv_to_rgb_matrix():
    m = np.array(extras.get_yuv_to_rgb_matrix("bt709")).reshape(3, 4)
    # Limited range: black (16, 128, 128) and white (235, 128, 128) of 8 bits
    black = m @ [16 / 255, 128 / 255, 128 / 255, 1]
    white = m @ [235 / 255, 128 / 255, 128 / 255, 1]
    assert np.allclose(black, 0, atol=1e-6) and np.allclose(white, 1, atol=1e-6)
    full = np.array(extras.get_yuv_to_rgb_matrix("bt601", full_range=True)).reshape(
        3, 4
    )
    assert np.allclose(full @ [1, 128 / 255, 128 / 255, 1], 1, atol=1e-6)
    # Pure red in BT.709 (Y, Cb, Cr) = (0.2126, -0.1146, 0.5) in full range
    full_709 = np.array(extras.get_yuv_to_rgb_matrix("bt709", full_range=True))
    red = full_709.reshape(3, 4) @ [0.2126, 128 / 255 - 0.1146, 128 / 255 + 0.5, 1]
    assert np.allclose(red, [1, 0, 0], atol=2e-3), red


NV12 = """
    import numpy as np
    extras.set_instance_extras(enable_toggles=["allow_unsafe_apis"])
    adapter = wgpu.gpu.request_adapter_sync()
    needed = ["dawn-multi-planar-formats", "multi-planar-format-extended-usages"]
    if not all(f in adapter.features for f in needed):
        print("SKIP adapter lacks", needed)
        raise SystemExit
    device = adapter.request_device_sync(required_features=needed)
    W, H = 4, 2
    texture = device.create_texture(
        size=(W, H, 1),
        format="r8bg8-biplanar-420-unorm",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    assert texture.format == "r8bg8-biplanar-420-unorm"
    Y = np.array([[16, 60, 120, 235], [100, 150, 200, 81]], np.uint8)
    UV = np.array([[[128, 128], [90, 240]]], np.uint8)
    device.queue.write_texture(
        {"texture": texture, "aspect": "plane0-only"}, Y, {"bytes_per_row": W}, (W, H, 1))
    device.queue.write_texture(
        {"texture": texture, "aspect": "plane1-only"}, UV, {"bytes_per_row": W},
        (W // 2, H // 2, 1))
    plane0 = texture.create_view(aspect="plane0-only")
    plane1 = texture.create_view(aspect="plane1-only")
    assert plane0.texture is texture

    shader = device.create_shader_module(code='''
        @group(0) @binding(0) var t: texture_external;
        @group(0) @binding(1) var<storage, read_write> out: array<vec4f>;
        @compute @workgroup_size(1) fn main(@builtin(global_invocation_id) i: vec3u) {
            out[i.y * textureDimensions(t).x + i.x] = textureLoad(t, i.xy);
        }
    ''')
    layout = device.create_bind_group_layout(entries=[
        {"binding": 0, "visibility": "COMPUTE", "external_texture": {}},
        {"binding": 1, "visibility": "COMPUTE", "buffer": {"type": "storage"}},
    ])
    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[layout]),
        compute={"module": shader, "entry_point": "main"},
    )

    def convert(external, size):
        out = device.create_buffer(size=size[0] * size[1] * 16, usage="STORAGE|COPY_SRC")
        bind_group = device.create_bind_group(layout=layout, entries=[
            {"binding": 0, "resource": external},
            {"binding": 1, "resource": {"buffer": out}},
        ])
        encoder = device.create_command_encoder()
        cpass = encoder.begin_compute_pass()
        cpass.set_pipeline(pipeline)
        cpass.set_bind_group(0, bind_group)
        cpass.dispatch_workgroups(*size)
        cpass.end()
        device.queue.submit([encoder.finish()])
        data = device.queue.read_buffer(out)
        return np.frombuffer(data, np.float32).reshape(size[1], size[0], 4)[..., :3]

    # Each pixel: the 3x4 matrix times (Y, U, V, 1), not clamped
    m = np.array(extras.get_yuv_to_rgb_matrix("bt709")).reshape(3, 4)
    uv = np.repeat(np.repeat(UV / 255, 2, 0), 2, 1)
    yuv = np.concatenate([Y[..., None] / 255, uv, np.ones((H, W, 1))], -1)
    expected = yuv @ m.T
    external = extras.create_external_texture(device, plane0, plane1, color_space="bt709")
    rgb = convert(external, (W, H))
    assert np.abs(rgb - expected).max() < 1e-3, (rgb, expected)

    # Crop and rotate: the shader sees the rotated 2x2 crop of the right half
    external = extras.create_external_texture(
        device, plane0, plane1, crop_origin=(2, 0), crop_size=(2, 2), rotation=90
    )
    rgb = convert(external, (2, 2))
    crop = expected[:, 2:]
    assert np.abs(rgb - np.rot90(crop, -1)).max() < 1e-3, (rgb, crop)
    print("OK")
"""


def test_nv12_external_texture():
    run_in_subprocess(NV12)
