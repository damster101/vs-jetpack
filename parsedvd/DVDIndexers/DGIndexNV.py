import vapoursynth as vs
from fractions import Fraction
from typing import Callable, List, Union, Optional
from functools import lru_cache, reduce as funcreduce


from ..utils.spathlib import SPath
from ..dataclasses import (
    DGIndexFileInfo, DGIndexFooter,
    DGIndexHeader, DGIndexFrameData, IndexFileVideo
)

from .DVDIndexer import DVDIndexer
from .utils import opt_int, opt_ints


core = vs.core


class DGIndexNV(DVDIndexer):
    """Built-in DGIndexNV indexer"""

    def __init__(
        self, path: Union[SPath, str] = 'DGIndexNV',
        vps_indexer: Optional[Callable[..., vs.VideoNode]] = None, ext: str = 'dgi'
    ) -> None:
        super().__init__(path, vps_indexer or core.dgdecodenv.DGSource, ext)

        return list(map(str, [self._check_path(), '-i', ','.join(map(str, files)), '-o', output, '-h']))
    def get_cmd(self, files: List[SPath], output: SPath) -> List[str]:

    def update_idx_file(self, index_path: Path, filepaths: List[Path]) -> None:
        with open(index_path, 'r') as file:
            file_content = file.read()

        lines = file_content.split('\n')

        str_filepaths = list(map(str, filepaths))

        if "DGIndexNV" not in lines[0]:
            self.file_corrupted(index_path)

        start_videos = lines.index('') + 1
        end_videos = lines.index('', start_videos)

        if (n_files := end_videos - start_videos) != len(str_filepaths):
            self.file_corrupted(index_path)

        split_videos = [
            [line[:-1], ' '.join(line[-1:])] for line in [
                line.split(' ') for line in lines[start_videos:end_videos]
            ]
        ]

        if [s[0] for s in split_videos] == str_filepaths:
            return

        lines[start_videos:end_videos] = [
            f"{filepaths[i]} {split_videos[i][1]}" for i in range(n_files)
        ]

        with open(index_path, 'w') as file:
            file.write('\n'.join(lines))

    @lru_cache
    def get_info(self, index_path: SPath, file_idx: int = 0) -> DGIndexFileInfo:
        with index_path.open(mode="r", encoding="utf8") as f:
            file_content = f.read()

        lines = file_content.split('\n')

        head, lines = self._split_lines(lines)

        if "DGIndexNV" not in head[0]:
            self.file_corrupted(index_path)

        vid_lines, lines = self._split_lines(lines)
        raw_header, lines = self._split_lines(lines)

        header = DGIndexHeader()

        for rlin in raw_header:
            if split_val := rlin.rstrip().split(' '):
                key: str = split_val[0].upper()
                values: List[str] = split_val[1:]
            else:
                continue

            if key == 'DEVICE':
                header.device = int(values[0])
            elif key == 'DECODE_MODES':
                header.decode_modes = list(map(int, values[0].split(',')))
            elif key == 'STREAM':
                header.stream = tuple(map(int, values))
            elif key == 'RANGE':
                header.ranges = list(map(int, values))
            elif key == 'DEMUX':
                continue
            elif key == 'DEPTH':
                header.depth = int(values[0])
            elif key == 'ASPECT':
                header.aspect = Fraction(*list(map(int, values)))
            elif key == 'COLORIMETRY':
                header.colorimetry = tuple(map(int, values))
            elif key == 'PKTSIZ':
                header.packet_size = int(values[0])
            elif key == 'VPID':
                header.vpid = int(values[0])

        videos = [
            IndexFileVideo(SPath(' '.join(line[:-1])), int(line[-1]))
            for line in map(lambda a: a.split(' '), vid_lines)
        ]

        max_sector = funcreduce(lambda a, b: a + b, [v.size for v in videos[:file_idx + 1]], 0)

        idx_file_sector = [max_sector - videos[file_idx].size, max_sector]

        curr_SEQ, frame_data = 0, []

        for rawline in lines:
            if len(rawline) == 0:
                break

            line: List[Optional[str]] = [*rawline.split(" ", maxsplit=6), *([None] * 6)]

            name = str(line[0])

            if name == 'SEQ':
                curr_SEQ = opt_int(line[1]) or 0

            if curr_SEQ < idx_file_sector[0]:
                continue
            elif curr_SEQ > idx_file_sector[1]:
                break

            try:
                int(name.split(':')[0])
            except ValueError:
                continue

            frame_data.append(DGIndexFrameData(
                int(line[2] or 0) + 2, str(line[1]), *opt_ints(line[4:6])
            ))

        footer = DGIndexFooter()

        for rlin in lines[-10:]:
            if split_val := rlin.rstrip().split(' '):
                values = [split_val[0], ' '.join(split_val[1:])]
            else:
                continue

            for key in footer.__dict__.keys():
                if key.split('_')[-1].upper() in values:
                    if key == 'film':
                        try:
                            value = [float(v.replace('%', '')) for v in values if '%' in v][0]
                        except IndexError:
                            value = 0
                    else:
                        value = int(values[1])

                    footer.__setattr__(key, value)

        return DGIndexFileInfo(index_path, file_idx, videos, header, frame_data, footer)
