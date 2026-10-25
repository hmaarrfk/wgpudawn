"""Tests specific to the Dawn backend (error handling, promises, lifetime)."""

import gc
import os
import sys
import asyncio
import subprocess

import numpy as np
import pytest

import wgpudawn as wgpu

import wgpudawn.backends.dawn as dawn


@pytest.fixture(scope="module")
def device():
    adapter = wgpu.gpu.request_adapter_sync()
    return adapter.request_device_sync()


COMPUTE_SHADER = """
@group(0) @binding(0) var<storage, read> data1: array<i32>;
@group(0) @binding(1) var<storage, read_write> data2: array<i32>;
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) index: vec3<u32>) {
    let i: u32 = index.x;
    data2[i] = data1[i] * 2 + 1;
}
"""

RENDER_SHADER = """
struct VertexOutput {
    @builtin(position) pos: vec4<f32>,
    @location(0) color: vec4<f32>,
};
@vertex
fn vs_main(@location(0) pos: vec2<f32>) -> VertexOutput {
    var out: VertexOutput;
    out.pos = vec4<f32>(pos, 0.0, 1.0);
    out.color = vec4<f32>(1.0, 0.5, 0.0, 1.0);
    return out;
}
@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return in.color;
}
"""


def test_backend_is_dawn():
    assert type(wgpu.gpu).__module__.startswith("wgpudawn.backends.dawn")
    adapter = wgpu.gpu.request_adapter_sync()
    assert isinstance(adapter, dawn.GPUAdapter)
    info = adapter.info
    assert isinstance(info["vendor"], str)
    assert info["backend_type"] in (
        "Vulkan",
        "Metal",
        "D3D12",
        "D3D11",
        "OpenGL",
        "OpenGLES",
    )
    assert adapter.limits["max-bind-groups"] >= 4
    assert "core-features-and-limits" in adapter.features or adapter.features


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Vulkan only")
def test_no_null_adapter_without_gpu():
    # Without a driver, Dawn returns its Null backend's adapter, which does
    # nothing: request_adapter must fail instead (so that code, and tests,
    # see that there is no GPU), unless the Null backend is asked for.
    code = """if True:
        import wgpudawn as wgpu
        assert wgpu.gpu.enumerate_adapters_sync() == []
        try:
            wgpu.gpu.request_adapter_sync()
        except RuntimeError as e:
            print("no adapter:", e)
        """
    env = {**os.environ, "VK_ICD_FILENAMES": "/nonexistent.json"}
    env.pop("WGPU_BACKEND_TYPE", None)
    for name in ("VK_DRIVER_FILES", "VK_ADD_DRIVER_FILES"):
        env.pop(name, None)
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True)
    assert p.returncode == 0, p.stderr.decode()
    assert "no adapter: " in p.stdout.decode()
    env["WGPU_BACKEND_TYPE"] = "Null"
    code = (
        "import wgpudawn as w; print(w.gpu.request_adapter_sync().info['backend_type'])"
    )
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True)
    assert p.returncode == 0, p.stderr.decode()
    assert p.stdout.decode().split() == ["Null"]


def test_request_device_with_features_and_limits():
    adapter = wgpu.gpu.request_adapter_sync()
    features = [
        f for f in ("float32-filterable", "timestamp-query") if f in adapter.features
    ]
    device = adapter.request_device_sync(
        required_features=features,
        required_limits={
            "max_bind_groups": 4,
            "max-storage-buffers-per-shader-stage": 8,
        },
    )
    assert isinstance(device, dawn.GPUDevice)
    for f in features:
        assert f in device.features
    assert device.limits["max-bind-groups"] == 4
    with pytest.raises(KeyError):
        adapter.request_device_sync(required_features=["not-a-feature"])


def test_buffer_upload_download(device):
    data = np.arange(64, dtype=np.uint32)
    buf = device.create_buffer_with_data(
        data=data, usage=wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
    )
    assert buf.size == data.nbytes
    out = np.frombuffer(device.queue.read_buffer(buf), np.uint32)
    assert np.all(out == data)

    # Partial write
    device.queue.write_buffer(buf, 8, np.array([100, 101], np.uint32))
    out = np.frombuffer(device.queue.read_buffer(buf), np.uint32)
    assert out[1] == 1 and out[2] == 100 and out[3] == 101 and out[4] == 4


def test_buffer_map_read_write(device):
    buf1 = device.create_buffer(
        size=64, usage=wgpu.BufferUsage.MAP_WRITE | wgpu.BufferUsage.COPY_SRC
    )
    buf2 = device.create_buffer(
        size=64, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST
    )
    data = np.arange(16, dtype=np.float32)

    buf1.map_sync("WRITE")
    assert buf1.map_state == "mapped"
    buf1.write_mapped(data)
    buf1.unmap()
    assert buf1.map_state == "unmapped"

    encoder = device.create_command_encoder()
    encoder.copy_buffer_to_buffer(buf1, 0, buf2, 0, 64)
    device.queue.submit([encoder.finish()])

    buf2.map_sync("READ")
    out1 = np.frombuffer(buf2.read_mapped(), np.float32)
    out2 = np.frombuffer(buf2.read_mapped(copy=False), np.float32).copy()
    buf2.unmap()
    assert np.all(out1 == data)
    assert np.all(out2 == data)


def test_compute(device):
    n = 64
    data = np.arange(n, dtype=np.int32)
    buf1 = device.create_buffer_with_data(data=data, usage=wgpu.BufferUsage.STORAGE)
    buf2 = device.create_buffer(
        size=data.nbytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
    )
    module = device.create_shader_module(code=COMPUTE_SHADER)
    pipeline = device.create_compute_pipeline(
        layout="auto", compute={"module": module, "entry_point": "main"}
    )
    bind_group = device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[
            {"binding": 0, "resource": {"buffer": buf1}},
            {
                "binding": 1,
                "resource": {"buffer": buf2, "offset": 0, "size": buf2.size},
            },
        ],
    )
    encoder = device.create_command_encoder()
    cpass = encoder.begin_compute_pass()
    cpass.set_pipeline(pipeline)
    cpass.set_bind_group(0, bind_group)
    cpass.dispatch_workgroups(n, 1, 1)
    cpass.end()
    device.queue.submit([encoder.finish()])
    out = np.frombuffer(device.queue.read_buffer(buf2), np.int32)
    assert np.all(out == data * 2 + 1)


def _render_square(device, use_bundle=False, use_index=False):
    size = 64
    fmt = "rgba8unorm"
    texture = device.create_texture(
        size=(size, size, 1),
        format=fmt,
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
    )
    # A square from -0.5 to 0.5
    vertices = np.array(
        [[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5]], np.float32
    )
    vbo = device.create_buffer_with_data(data=vertices, usage=wgpu.BufferUsage.VERTEX)
    indices = np.array([0, 1, 2, 2, 1, 3], np.uint32)
    ibo = device.create_buffer_with_data(data=indices, usage=wgpu.BufferUsage.INDEX)
    module = device.create_shader_module(code=RENDER_SHADER)
    pipeline = device.create_render_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[]),
        vertex={
            "module": module,
            "entry_point": "vs_main",
            "buffers": [
                {
                    "array_stride": 8,
                    "attributes": [
                        {"format": "float32x2", "offset": 0, "shader_location": 0}
                    ],
                }
            ],
        },
        primitive={"topology": "triangle-list" if use_index else "triangle-strip"},
        fragment={
            "module": module,
            "entry_point": "fs_main",
            "targets": [{"format": fmt}],
        },
    )

    def record(enc):
        enc.set_pipeline(pipeline)
        enc.set_vertex_buffer(0, vbo)
        if use_index:
            enc.set_index_buffer(ibo, "uint32")
            enc.draw_indexed(6)
        else:
            enc.draw(4)

    encoder = device.create_command_encoder()
    rpass = encoder.begin_render_pass(
        color_attachments=[
            {
                "view": texture.create_view(),
                "load_op": "clear",
                "store_op": "store",
                "clear_value": (0, 0, 0.5, 1),
            }
        ]
    )
    if use_bundle:
        bundle_encoder = device.create_render_bundle_encoder(color_formats=[fmt])
        record(bundle_encoder)
        rpass.execute_bundles([bundle_encoder.finish()])
    else:
        record(rpass)
    rpass.end()
    device.queue.submit([encoder.finish()])

    data = device.queue.read_texture(
        {"texture": texture}, {"bytes_per_row": size * 4}, (size, size, 1)
    )
    return np.frombuffer(data, np.uint8).reshape(size, size, 4)


@pytest.mark.parametrize("use_bundle", [False, True])
@pytest.mark.parametrize("use_index", [False, True])
def test_render_to_texture(device, use_bundle, use_index):
    im = _render_square(device, use_bundle, use_index)
    # Center is orange, corners are the clear color
    assert tuple(im[32, 32]) in ((255, 128, 0, 255), (255, 127, 0, 255))
    assert tuple(im[2, 2]) in ((0, 0, 128, 255), (0, 0, 127, 255))
    n_orange = np.sum(im[:, :, 1] > 100)
    assert n_orange == 32 * 32


def test_validation_error_raises_at_call_site(device):
    with pytest.raises(wgpu.GPUValidationError) as err:
        device.create_buffer(
            size=64, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.STORAGE
        )
    assert "MapRead" in str(err.value)
    # And the next call is fine again
    device.create_buffer(size=64, usage=wgpu.BufferUsage.MAP_READ)


def test_shader_error_raises(device):
    with pytest.raises(wgpu.GPUValidationError) as err:
        device.create_shader_module(
            code="@compute @workgroup_size(1) fn main() { let x: f32 = 1u; }"
        )
    assert "error" in str(err.value).lower()


def test_compilation_info(device):
    module = device.create_shader_module(code=COMPUTE_SHADER)
    info = module.get_compilation_info_sync()
    assert isinstance(info, wgpu.GPUCompilationInfo)
    assert isinstance(info.messages, list)


def test_error_scopes(device):
    device.push_error_scope("validation")
    device.create_buffer(
        size=64, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.STORAGE
    )
    error = device.pop_error_scope_async().sync_wait()
    assert isinstance(error, wgpu.GPUValidationError)
    device.push_error_scope("validation")
    error = device.pop_error_scope_async().sync_wait()
    assert error is None


def test_released_objects(device):
    buf = device.create_buffer(size=64, usage=wgpu.BufferUsage.COPY_DST)
    buf._release()
    assert buf._internal is None
    with pytest.raises(RuntimeError):
        device.queue.write_buffer(buf, 0, b"0000")
    # Lots of objects being created and garbage collected
    for _ in range(100):
        device.create_buffer(size=64, usage=wgpu.BufferUsage.COPY_DST)
    gc.collect()


def test_async_await(device):
    buf = device.create_buffer_with_data(
        data=np.arange(16, dtype=np.uint32), usage=wgpu.BufferUsage.COPY_SRC
    )
    buf2 = device.create_buffer(
        size=buf.size, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST
    )
    encoder = device.create_command_encoder()
    encoder.copy_buffer_to_buffer(buf, 0, buf2, 0, buf.size)
    device.queue.submit([encoder.finish()])

    results = []

    async def main():
        await device.queue.on_submitted_work_done_async()
        await buf2.map_async("READ")
        results.append(np.frombuffer(buf2.read_mapped(), np.uint32).copy())
        buf2.unmap()
        # Using then()
        event = asyncio.Event()
        promise = device.queue.on_submitted_work_done_async()
        promise.then(lambda _: event.set())
        await asyncio.wait_for(event.wait(), 5)
        results.append("then")

    asyncio.run(main())
    assert np.all(results[0] == np.arange(16))
    assert results[1] == "then"


def test_device_lost_on_destroy():
    adapter = wgpu.gpu.request_adapter_sync()
    device = adapter.request_device_sync()
    promise = device._get_lost_async()
    device.destroy()
    dawn.process_events()
    info = promise.sync_wait()
    assert info.reason == "destroyed"


def test_bind_group_resources():
    # make sure every resource type can be created in a bind group.
    device = wgpu.utils.get_default_device()

    sampler = device.create_sampler()
    texture1 = device.create_texture(
        label="texture1",
        size=(8, 8, 1),
        format=wgpu.TextureFormat.rgba8unorm,
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    texture2 = device.create_texture(
        label="texture2",
        size=(8, 8, 1),
        format=wgpu.TextureFormat.rgba8unorm,
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    texture_view = texture2.create_view()

    buffer = device.create_buffer(
        size=256,
        usage=wgpu.BufferUsage.UNIFORM,
    )

    entires = [
        wgpu.structs.BindGroupEntry(binding=0, resource=sampler),
        wgpu.structs.BindGroupEntry(binding=1, resource=texture1),
        wgpu.structs.BindGroupEntry(binding=2, resource=texture_view),
        wgpu.structs.BindGroupEntry(
            binding=3,
            resource=buffer,
        ),
        wgpu.structs.BindGroupEntry(
            binding=4,
            resource=wgpu.structs.BufferBinding(
                buffer=buffer,
            ),
        ),
        # maybe external texture one day
    ]

    # maybe we should write a bit of compute shader so we can use auto layout mode instead.
    layout_entries = [
        wgpu.BindGroupLayoutEntry(
            binding=0,
            visibility=wgpu.ShaderStage.COMPUTE,
            sampler=wgpu.structs.SamplerBindingLayout(),
        ),
        wgpu.BindGroupLayoutEntry(
            binding=1,
            visibility=wgpu.ShaderStage.COMPUTE,
            texture=wgpu.structs.TextureBindingLayout(),
        ),
        wgpu.BindGroupLayoutEntry(
            binding=2,
            visibility=wgpu.ShaderStage.COMPUTE,
            texture=wgpu.structs.TextureBindingLayout(),
        ),
        wgpu.BindGroupLayoutEntry(
            binding=3,
            visibility=wgpu.ShaderStage.COMPUTE,
            buffer=wgpu.structs.BufferBindingLayout(),
        ),
        wgpu.BindGroupLayoutEntry(
            binding=4,
            visibility=wgpu.ShaderStage.COMPUTE,
            buffer=wgpu.structs.BufferBindingLayout(),
        ),
    ]

    layout = device.create_bind_group_layout(entries=layout_entries)

    bind_group = device.create_bind_group(layout=layout, entries=entires)

    assert bind_group


def test_aspects_of_views_and_copies():
    # A view of one aspect takes that aspect's format by default, and copies
    # use the aspect that is given (both were always "all" before)
    device = wgpu.utils.get_default_device()
    texture = device.create_texture(
        size=(4, 4, 1),
        format="depth24plus-stencil8",
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT
        | wgpu.TextureUsage.TEXTURE_BINDING
        | wgpu.TextureUsage.COPY_SRC,
    )
    view = texture.create_view(aspect="stencil-only")
    assert view.texture is texture
    texture.create_view(aspect="depth-only")

    encoder = device.create_command_encoder()
    rpass = encoder.begin_render_pass(
        color_attachments=[],
        depth_stencil_attachment={
            "view": texture.create_view(),
            "depth_clear_value": 1.0,
            "depth_load_op": "clear",
            "depth_store_op": "store",
            "stencil_clear_value": 7,
            "stencil_load_op": "clear",
            "stencil_store_op": "store",
        },
    )
    rpass.end()
    buffer = device.create_buffer(size=256 * 4, usage="COPY_DST|COPY_SRC")
    encoder.copy_texture_to_buffer(
        {"texture": texture, "aspect": "stencil-only"},
        {"buffer": buffer, "bytes_per_row": 256},
        (4, 4, 1),
    )
    device.queue.submit([encoder.finish()])
    data = np.frombuffer(device.queue.read_buffer(buffer), np.uint8).reshape(4, 256)
    assert (data[:, :4] == 7).all()
