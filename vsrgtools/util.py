from __future__ import annotations

from typing import Any, Sequence, TypeVar

from vstools import (
    ConstantFormatVideoNode, GenericVSFunction, KwargsT, Nb, PlanesT, check_variable, check_variable_format,
    join, normalize_planes, normalize_seq, plane, vs
)

from .enum import RemoveGrainMode, RepairMode

__all__ = [
    'norm_rmode_planes',
    'normalize_radius'
]

RModeT = TypeVar('RModeT', RemoveGrainMode, RepairMode)


def norm_rmode_planes(
    clip: vs.VideoNode, mode: int | RModeT | Sequence[int | RModeT], planes: PlanesT = None
) -> list[int]:
    assert check_variable(clip, norm_rmode_planes)

    modes_array = normalize_seq(mode, clip.format.num_planes)

    planes = normalize_planes(clip, planes)

    return [rep if i in planes else 0 for i, rep in enumerate(modes_array, 0)]


def normalize_radius(
    clip: vs.VideoNode, func: GenericVSFunction[ConstantFormatVideoNode], radius: list[Nb] | tuple[str, list[Nb]],
    planes: PlanesT, **kwargs: Any
) -> ConstantFormatVideoNode:
    assert check_variable_format(clip, normalize_radius)

    name, radius = radius if isinstance(radius, tuple) else ('radius', radius)

    radius = normalize_seq(radius, clip.format.num_planes)

    planes = normalize_planes(clip, planes)

    def _get_kwargs(rad: Nb) -> KwargsT:
        return kwargs | {name: rad, 'planes': planes}

    if len(set(radius)) > 0:
        if len(planes) != 1:
            return join([
                func(plane(clip, i), **_get_kwargs(rad)) for i, rad in enumerate(radius)
            ])

        radius_i = radius[planes[0]]
    else:
        radius_i = radius[0]

    return func(clip, **_get_kwargs(radius_i))
