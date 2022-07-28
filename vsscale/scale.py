
import sys
from dataclasses import dataclass
from functools import partial
from typing import Tuple

import vapoursynth as vs
from vsexprtools import expr_func
from vsexprtools.util import aka_expr_available
from vskernels import Catrom, get_kernel, get_matrix
from vskernels.kernels.abstract import Scaler
from vskernels.types import VSFunction
from vsrgtools import box_blur, gauss_blur
from vsutil import depth, fallback, get_depth, get_w

from .gamma import gamma2linear, linear2gamma
from .types import TransferCurve

__all__ = [
    'SSIM', 'ssim_downsample'
]

core = vs.core


@dataclass
class SSIM(Scaler):
    smooth: float | VSFunction = ((3 ** 2 - 1) / 12) ** 0.5
    curve: TransferCurve | bool = False
    sigmoid: bool = False
    scaler: Scaler = Catrom()

    def scale(self, clip: vs.VideoNode, width: int, height: int, shift: Tuple[float, float] = (0, 0)) -> vs.VideoNode:
        return ssim_downsample(clip, width, height, self.smooth, self.scaler, self.curve, self.sigmoid, shift)


def ssim_downsample(
    clip: vs.VideoNode, width: int | None = None, height: int = 720,
    smooth: float | VSFunction = ((3 ** 2 - 1) / 12) ** 0.5,
    scaler: Scaler | str = Catrom(),
    curve: TransferCurve | bool = False, sigmoid: bool = False,
    shift: Tuple[float, float] = (0, 0)
) -> vs.VideoNode:
    """
    SSIM downsampler is an image downscaling technique that aims to optimize
    for the perceptual quality of the downscaled results.
    Image downscaling is considered as an optimization problem
    where the difference between the input and output images is measured
    using famous Structural SIMilarity (SSIM) index.
    The solution is derived in closed-form, which leads to the simple, efficient implementation.
    The downscaled images retain perceptually important features and details,
    resulting in an accurate and spatio-temporally consistent representation of the high resolution input.

    `Original gist <https://gist.github.com/Ichunjo/16ab1f893588aafcb096c1f35a0cfb15>`_

    :param clip:        Clip to process.
    :param width:       Output width. If None, autocalculates using height.
    :param height:      Output height (Default: 720).
    :param smooth:      Image smoothening method.
                        If you pass an int, it specifies the "radius" of the internally-used boxfilter,
                        i.e. the window has a size of (2*smooth+1)x(2*smooth+1).
                        If you pass a float, it specifies the "sigma" of gauss_blur,
                        i.e. the standard deviation of gaussian blur.
                        If you pass a function, it acts as a general smoother.
                        Default uses a gaussian blur.
    :param scaler:      Scaler object used for certain scaling operations.
                        This can also be the string name of the kernel.
    :param curve:       Perform a gamma conversion prior to scaling and after scaling.
                        This must be set for `sigmoid` to function.
                        If True it will auto-determine the curve based on the input props or resolution.
                        Can be specified with for example `curve=TransferCurve.BT709`.
    :param sigmoid:     When True, applies a sigmoidal curve after the power-like curve
                        (or before when converting from linear to gamma-corrected).
                        This helps reduce the dark halo artefacts found around sharp edges
                        caused by resizing in linear luminance.
                        This parameter only works if `gamma=True`.
    :param shift:       Shift passed to the kernel.

    :return:            Downsampled clip.
    """
    assert clip.format

    epsilon = sys.float_info.epsilon

    if isinstance(scaler, str):
        scaler = get_kernel(scaler)()
    elif isinstance(scaler, SSIM):
        raise ValueError("SSIM: you can't have SSIM as a scaler for itself!")

    if callable(smooth):
        filter_func = smooth
    elif isinstance(smooth, int):
        filter_func = partial(box_blur, radius=smooth)
    elif isinstance(smooth, float):
        filter_func = partial(gauss_blur, sigma=smooth)

    width = fallback(width, get_w(height, aspect_ratio=clip.width / clip.height))

    if curve is True:
        curve = TransferCurve.from_matrix(get_matrix(clip))

    bits, clip = get_depth(clip), depth(clip, 32)

    if curve:
        clip = gamma2linear(clip, curve, sigmoid=sigmoid, epsilon=epsilon)

    l1 = scaler.scale(clip, width, height, shift)

    l1_sq, c_sq = [x.akarin.Expr('x dup *') for x in (l1, clip)]

    l2 = scaler.scale(c_sq, width, height, shift)

    m, sl_m_square, sh_m_square = [filter_func(x) for x in (l1, l1_sq, l2)]

    if aka_expr_available:
        merge_expr = f'z dup * SQ! x SQ@ - SQD! SQD@ {epsilon} < 0 y SQ@ - SQD@ / sqrt ?'
    else:
        merge_expr = f'x z dup * - {epsilon} < 0 y z dup * - x z dup * - / sqrt ?'

    r = expr_func([sl_m_square, sh_m_square, m], merge_expr)
    t = expr_func([r, m], 'x y *')
    d = expr_func([filter_func(m), filter_func(r), l1, filter_func(t)], 'x y z * + a -')

    if curve:
        d = linear2gamma(d, curve, sigmoid=sigmoid)

    return depth(d, bits)
