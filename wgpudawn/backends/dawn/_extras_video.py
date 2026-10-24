"""Dawn's native extras for video: external textures, which sample planes of
YUV data (multi-planar formats such as NV12 and P010) as RGB. See extras.py.
"""

from typing import Sequence, Union

from ._api import (
    GPUDevice,
    GPUExternalTexture,
    GPUTextureView,
    ffi,
    lib,
    new_struct,
    new_struct_p,
    to_c_string_view,
)
from ._extras_util import _native


# Luma coefficients (Kr, Kb) of the YUV color spaces
_color_spaces = {
    "bt601": (0.299, 0.114),
    "bt709": (0.2126, 0.0722),
    "bt2020": (0.2627, 0.0593),
}

_rotations = {0: "Rotate0Degrees", 90: "Rotate90Degrees", 180: "Rotate180Degrees"}
_rotations[270] = "Rotate270Degrees"

# skcms transfer function parameters (g, a, b, c, d, e, f) of the identity,
# and the identity gamut conversion
_IDENTITY_TRANSFER = (1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0)
_IDENTITY_GAMUT = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def get_yuv_to_rgb_matrix(color_space="bt709", *, full_range=False, bits=8):
    """The 3x4 matrix (12 floats, row-major) that converts normalized
    ``(Y, U, V, 1)`` to RGB, for a color space (``"bt601"``, ``"bt709"`` or
    ``"bt2020"``) and range: limited ("TV", e.g. 16-235 for 8 bits, the
    default for video) or full."""
    kr, kb = _color_spaces[color_space]
    kg = 1.0 - kr - kb
    scale = float((1 << bits) - 1)
    center = (1 << (bits - 1)) / scale
    if full_range:
        y_scale, y_offset, c_scale = 1.0, 0.0, 1.0
    else:
        y_scale = scale / (219 << (bits - 8))
        y_offset = (16 << (bits - 8)) / scale
        c_scale = scale / (224 << (bits - 8))
    rows = (
        (0.0, 2 * (1 - kr)),  # R: (U, V) coefficients
        (-2 * kb * (1 - kb) / kg, -2 * kr * (1 - kr) / kg),  # G
        (2 * (1 - kb), 0.0),  # B
    )
    matrix = []
    for u, v in rows:
        u, v = u * c_scale, v * c_scale
        matrix += [y_scale, u, v, -y_scale * y_offset - (u + v) * center]
    return tuple(matrix)


def create_external_texture(
    device: GPUDevice,
    plane0: GPUTextureView,
    plane1: Union[GPUTextureView, None] = None,
    *,
    label: str = "",
    color_space: str = "bt709",
    full_range: bool = False,
    yuv_to_rgb_matrix: Union[Sequence[float], None] = None,
    src_transfer_function: Union[Sequence[float], None] = None,
    dst_transfer_function: Union[Sequence[float], None] = None,
    gamut_conversion_matrix: Union[Sequence[float], None] = None,
    crop_origin=(0, 0),
    crop_size=None,
    apparent_size=None,
    mirrored: bool = False,
    rotation: int = 0,
) -> GPUExternalTexture:
    """Create an external texture: what a shader samples as
    ``texture_external`` (with ``textureSampleBaseClampToEdge`` or
    ``textureLoad``), converted to RGB on the fly. Bind it with
    ``{"binding": i, "visibility": ..., "external_texture": {}}`` in the
    layout and the external texture as the resource.

    Arguments:
        device (GPUDevice): The device.
        plane0 (GPUTextureView): The luma (Y) plane, e.g. the ``"plane0-only"``
            view of an ``r8bg8-biplanar-420-unorm`` (NV12) texture; or an RGBA
            view, then without ``plane1``.
        plane1 (GPUTextureView): The chroma (UV) plane, e.g. the
            ``"plane1-only"`` view.
        label (str): A human-readable label. Optional.
        color_space (str): The YUV color space: ``"bt601"``, ``"bt709"``
            or ``"bt2020"``.
        full_range (bool): Whether the YUV values are full range (JPEG) rather
            than limited range (video).
        yuv_to_rgb_matrix (list of 12 floats): Instead of ``color_space``
            and ``full_range``: the 3x4 matrix, see :func:`get_yuv_to_rgb_matrix`.
        src_transfer_function, dst_transfer_function (list of 7 floats): For
            color-managed output: the transfer functions (skcms parameters g, a,
            b, c, d, e, f) to linearize the source and to encode for the
            destination, with ``gamut_conversion_matrix`` (9 floats, 3x3) in
            between. If none of them is given, only the YUV to RGB conversion
            is done.
        crop_origin (tuple): The origin of the visible rectangle.
        crop_size (tuple): Its size; by default that of ``plane0``.
        apparent_size (tuple): The size of the texture in the shader (e.g. of
            a rotated or scaled frame); by default ``crop_size``.
        mirrored (bool): Mirror horizontally.
        rotation (int): 0, 90, 180 or 270 degrees.
    """
    if not isinstance(plane0, GPUTextureView):
        raise TypeError("plane0 must be a GPUTextureView")
    if plane1 is not None and not isinstance(plane1, GPUTextureView):
        raise TypeError("plane1 must be a GPUTextureView or None")
    if rotation not in _rotations:
        raise ValueError("rotation must be 0, 90, 180 or 270")
    color_managed = any(
        x is not None
        for x in (src_transfer_function, dst_transfer_function, gamut_conversion_matrix)
    )

    def floats(values, n, what):
        values = tuple(float(x) for x in values)
        if len(values) != n:
            raise ValueError(f"{what} must have {n} values")
        return ffi.new("float[]", values)

    keep_alive = []
    if plane1 is not None:
        if yuv_to_rgb_matrix is None:
            yuv_to_rgb_matrix = get_yuv_to_rgb_matrix(
                color_space, full_range=full_range
            )
        c_matrix = floats(yuv_to_rgb_matrix, 12, "yuv_to_rgb_matrix")
        keep_alive.append(c_matrix)
    else:
        c_matrix = ffi.NULL
    c_src = floats(
        src_transfer_function or _IDENTITY_TRANSFER, 7, "src_transfer_function"
    )
    c_dst = floats(
        dst_transfer_function or _IDENTITY_TRANSFER, 7, "dst_transfer_function"
    )
    c_gamut = floats(
        gamut_conversion_matrix or _IDENTITY_GAMUT, 9, "gamut_conversion_matrix"
    )
    keep_alive += [c_src, c_dst, c_gamut]

    size = plane0.texture.size
    if crop_size is None:
        crop_size = (size[0] - crop_origin[0], size[1] - crop_origin[1])
    if apparent_size is None:
        apparent_size = crop_size
        if rotation in (90, 270):
            apparent_size = crop_size[::-1]

    struct = new_struct_p(
        "WGPUExternalTextureDescriptor *",
        label=to_c_string_view(label),
        plane0=plane0._internal,
        plane1=plane1._internal if plane1 is not None else ffi.NULL,
        cropOrigin=new_struct("WGPUOrigin2D", x=crop_origin[0], y=crop_origin[1]),
        cropSize=new_struct("WGPUExtent2D", width=crop_size[0], height=crop_size[1]),
        apparentSize=new_struct(
            "WGPUExtent2D", width=apparent_size[0], height=apparent_size[1]
        ),
        doYuvToRgbConversionOnly=plane1 is not None and not color_managed,
        yuvToRgbConversionMatrix=c_matrix,
        srcTransferFunctionParameters=c_src,
        dstTransferFunctionParameters=c_dst,
        gamutConversionMatrix=c_gamut,
        mirrored=bool(mirrored),
        rotation=getattr(lib, f"WGPUExternalTextureRotation_{_rotations[rotation]}"),
    )
    id = _native("wgpuDeviceCreateExternalTexture")(device._internal, struct)
    texture = GPUExternalTexture(label, id, device)
    texture._planes = (plane0, plane1)  # Dawn reads them when sampling
    return texture
