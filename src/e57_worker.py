"""Isolated E57 I/O. Run through launch.py --e57-worker in packaged builds."""
import json
import sys
from pathlib import Path
import numpy as np
import pye57
from scipy.spatial.transform import Rotation
from src.transforms import rigid_matrix


def extract(source, folder, max_points=20_000_000):
    folder = Path(folder)
    with pye57.E57(source) as reader:
        count = sum(reader.get_header(i).point_count for i in range(reader.scan_count))
        if count > max_points:
            raise ValueError(f'E57 exceeds the interactive limit ({max_points:,} points). Tile a copy first.')
        if count == 0:
            raise ValueError('E57 contains no points.')
        points = np.lib.format.open_memmap(folder/'points.npy', mode='w+', dtype='float64', shape=(count, 3))
        colors = np.lib.format.open_memmap(folder/'colors.npy', mode='w+', dtype='float64', shape=(count, 3))
        intensity = np.lib.format.open_memmap(folder/'intensity.npy', mode='w+', dtype='float64', shape=(count,))
        offset, scans, all_color = 0, [], True
        for i in range(reader.scan_count):
            header = reader.get_header(i)
            data = reader.read_scan(i, colors=True, intensity=True, transform=True, ignore_missing_fields=True)
            xyz = np.column_stack([data['cartesian'+a] for a in 'XYZ'])
            valid = np.isfinite(xyz).all(axis=1)
            xyz = xyz[valid]
            end = offset + len(xyz)
            points[offset:end] = xyz
            has_color = all('color'+a in data for a in ['Red','Green','Blue'])
            all_color &= has_color
            if has_color:
                colors[offset:end] = np.column_stack([data['color'+a][valid] for a in ['Red','Green','Blue']]) / 255.0
            intensity[offset:end] = data['intensity'][valid] if 'intensity' in data else np.nan
            scans.append({'index': i, 'start': offset, 'stop': end, 'name': header['name'].value() if header.node.isDefined('name') else f'Scan {i}',
                          'rotation_wxyz': np.asarray(header.rotation).tolist(), 'translation': np.asarray(header.translation).tolist()})
            offset = end
        points.flush(); colors.flush(); intensity.flush()
        (folder/'metadata.json').write_text(json.dumps({'count': offset, 'has_colors': all_color, 'scans': scans}))


def transform_file(source, destination, matrix):
    matrix = rigid_matrix(matrix)
    with pye57.E57(source) as reader:
        if reader.root.isDefined('images2D') and reader.root['images2D'].childCount():
            raise ValueError('E57 contains embedded images, which native export cannot preserve. Use a PLY derivative or an image-preserving E57 conversion workflow.')
        if reader.root.isDefined('coordinateMetadata') and reader.root['coordinateMetadata'].value().strip():
            raise ValueError('E57 contains coordinate reference metadata that this writer cannot safely copy. Use a PLY derivative with the alignment report or an E57 converter that preserves the CRS.')
    with pye57.E57(source) as reader, pye57.E57(destination, mode='w') as writer:
        for i in range(reader.scan_count):
            header = reader.get_header(i)
            data = reader.read_scan_raw(i, ignore_unsupported_fields=False)
            # Keep raw samples and supported attributes in scanner coordinates;
            # compose the world-space alignment into each individual scan pose.
            if not all('cartesian'+a in data for a in 'XYZ'):
                raise ValueError('Spherical E57 export requires a Cartesian conversion first.')
            pose = np.eye(4)
            q = np.asarray(header.rotation)
            pose[:3,:3] = Rotation.from_quat(q[[1,2,3,0]]).as_matrix()
            pose[:3,3] = header.translation
            result = matrix @ pose
            q = Rotation.from_matrix(result[:3,:3]).as_quat()[[3,0,1,2]]
            writer.write_scan_raw(data, name=header['name'].value() if header.node.isDefined('name') else f'Scan {i}', rotation=q, translation=result[:3,3], scan_header=header)
    with pye57.E57(source) as reader, pye57.E57(destination) as check:
        if reader.scan_count != check.scan_count:
            raise RuntimeError('E57 scan count changed during export.')
        for i in range(reader.scan_count):
            raw_a=reader.read_scan_raw(i,ignore_unsupported_fields=False)
            raw_b=check.read_scan_raw(i,ignore_unsupported_fields=False)
            for key in raw_a:
                if key not in raw_b or not np.array_equal(raw_a[key],raw_b[key],equal_nan=True):
                    raise RuntimeError(f'E57 raw attribute {key} changed.')
            a = reader.read_scan(i, colors=True, intensity=True, transform=True, ignore_missing_fields=True)
            b = check.read_scan(i, colors=True, intensity=True, transform=True, ignore_missing_fields=True)
            xyz = np.column_stack([a['cartesian'+k] for k in 'XYZ'])
            actual = np.column_stack([b['cartesian'+k] for k in 'XYZ'])
            if not np.allclose(actual, xyz @ matrix[:3,:3].T + matrix[:3,3], atol=1e-7, rtol=0):
                raise RuntimeError('E57 world coordinates failed export validation.')
            for key in a:
                if not key.startswith('cartesian') and not np.array_equal(a[key], b[key]):
                    raise RuntimeError(f'E57 attribute {key} changed.')


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args[0] == 'extract':
        extract(args[1], args[2], int(args[3]) if len(args)>3 else 20_000_000)
    elif args[0] == 'transform':
        transform_file(args[1], args[2], np.load(args[3], allow_pickle=False))
    else:
        raise ValueError('Unknown E57 operation.')

if __name__ == '__main__':
    main()
