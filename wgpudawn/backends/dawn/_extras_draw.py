"""wgpu-py's extras (``wgpu.backends.wgpu_native.extras``) that Dawn can do,
with the same signatures. See extras.py."""

from ._api import (
    GPUBuffer,
    GPUCommandEncoder,
    GPUComputePassEncoder,
    GPUQuerySet,
    GPURenderPassEncoder,
)


def multi_draw_indirect(
    render_pass_encoder: GPURenderPassEncoder,
    buffer: GPUBuffer,
    *,
    offset: int = 0,
    count: int,
):
    """
    This is equivalent to
    for i in range(count):
        render_pass_encoder.draw(buffer, offset + i * 16)

    You must enable the feature "multi-draw-indirect" to use this function
    (experimental in Dawn, see ``set_instance_extras(enable_toggles=["allow_unsafe_apis"])``).
    """
    render_pass_encoder._multi_draw_indirect(buffer, offset, count)


def multi_draw_indexed_indirect(
    render_pass_encoder: GPURenderPassEncoder,
    buffer: GPUBuffer,
    *,
    offset: int = 0,
    count: int,
):
    """
    This is equivalent to

    for i in range(count):
        render_pass_encoder.draw_indexed(buffer, offset + i * 20)

    You must enable the feature "multi-draw-indirect" to use this function
    (experimental in Dawn, see ``set_instance_extras(enable_toggles=["allow_unsafe_apis"])``).
    """
    render_pass_encoder._multi_draw_indexed_indirect(buffer, offset, count)


def multi_draw_indirect_count(
    render_pass_encoder: GPURenderPassEncoder,
    buffer: GPUBuffer,
    *,
    offset: int = 0,
    count_buffer: GPUBuffer,
    count_buffer_offset: int = 0,
    max_count: int,
):
    """
    This is equivalent to:

    count = min(<u32 at offset count_buffer_offset of count_buffer>, max_count)
    for i in range(count):
        render_pass_encoder.draw(buffer, offset + i * 16)

    You must enable the feature "multi-draw-indirect" to use this function
    (Dawn has one feature for both; it is experimental, see
    ``set_instance_extras(enable_toggles=["allow_unsafe_apis"])``).
    """
    render_pass_encoder._multi_draw_indirect_count(
        buffer, offset, count_buffer, count_buffer_offset, max_count
    )


def multi_draw_indexed_indirect_count(
    render_pass_encoder: GPURenderPassEncoder,
    buffer: GPUBuffer,
    *,
    offset: int = 0,
    count_buffer: GPUBuffer,
    count_buffer_offset: int = 0,
    max_count: int,
):
    """
    This is equivalent to:

    count = min(<u32 at offset count_buffer_offset of count_buffer>, max_count)
    for i in range(count):
        render_pass_encoder.draw_indexed(buffer, offset + i * 20)

    You must enable the feature "multi-draw-indirect" to use this function
    (Dawn has one feature for both; it is experimental, see
    ``set_instance_extras(enable_toggles=["allow_unsafe_apis"])``).
    """
    render_pass_encoder._multi_draw_indexed_indirect_count(
        buffer, offset, count_buffer, count_buffer_offset, max_count
    )


def write_timestamp(
    encoder: GPURenderPassEncoder | GPUComputePassEncoder | GPUCommandEncoder,
    query_set: GPUQuerySet,
    query_index: int,
):
    """Write a timestamp into a query set from a command encoder, or from a
    render or compute pass.

    Dawn needs the ``timestamp-query`` feature and the ``allow_unsafe_apis``
    toggle (``set_instance_extras(enable_toggles=["allow_unsafe_apis"])``);
    inside a pass also the ``chromium-experimental-timestamp-query-inside-passes``
    feature.
    """
    assert isinstance(
        encoder, (GPURenderPassEncoder, GPUComputePassEncoder, GPUCommandEncoder)
    )
    encoder._write_timestamp(query_set, query_index)
