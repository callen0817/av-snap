"""Atomic IFC engineering-coordinate export, preserving the placement graph."""
import os
import tempfile
from pathlib import Path
import numpy as np
import ifcopenshell
from ifcopenshell.util.placement import get_local_placement
from ifcopenshell.util.unit import calculate_unit_scale
from src.transforms import rigid_matrix


def _products(model):
    result = {}
    for product in model.by_type('IfcProduct'):
        p = product.ObjectPlacement
        if p is not None:
            if not p.is_a('IfcLocalPlacement'):
                raise ValueError('IFC grid/linear placements require conversion to local placements before alignment.')
            result[product.id()] = get_local_placement(p)
    if not result:
        raise ValueError('IFC contains no placed products to transform.')
    return result


def export_ifc(source, destination, transform):
    transform = rigid_matrix(transform)
    if Path(source).resolve() == Path(destination).resolve() or (os.path.exists(destination) and os.path.samefile(source, destination)):
        raise ValueError('Choose a new IFC filename; the source model must be preserved.')
    model = ifcopenshell.open(str(source))
    scale = calculate_unit_scale(model)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid IFC length units.')
    before = _products(model)
    roots = {}
    for product_id in before:
        p = model.by_id(product_id).ObjectPlacement
        seen = set()
        while p.PlacementRelTo:
            if p.id() in seen:
                raise ValueError('Cyclic IFC placement hierarchy.')
            seen.add(p.id())
            p = p.PlacementRelTo
            if not p.is_a('IfcLocalPlacement'):
                raise ValueError('Unsupported parent placement type.')
        roots[p.id()] = p
    # Replace only each root's relative axis placement. Children and shared
    # placements remain intact, so the world transform is applied exactly once.
    local_transform = transform.copy()
    local_transform[:3, 3] /= scale
    original_entities = {e.id(): e.to_string() for e in model if e.id() not in roots}
    for root in roots.values():
        new = local_transform @ get_local_placement(root)
        origin = model.create_entity('IfcCartesianPoint', tuple(map(float, new[:3, 3])))
        axis = model.create_entity('IfcDirection', tuple(map(float, new[:3, 2])))
        ref = model.create_entity('IfcDirection', tuple(map(float, new[:3, 0])))
        root.RelativePlacement = model.create_entity('IfcAxis2Placement3D', origin, axis, ref)
    folder = Path(destination).resolve().parent
    fd, temporary = tempfile.mkstemp(prefix='.av-snap-', suffix='.ifc', dir=folder)
    os.close(fd)
    try:
        model.write(temporary)
        check = ifcopenshell.open(temporary)
        after = _products(check)
        if set(before) != set(after):
            raise RuntimeError('IFC validation failed: product inventory changed.')
        for product_id, matrix in before.items():
            expected = local_transform @ matrix
            if not np.allclose(after[product_id], expected, atol=1e-6 / scale, rtol=0):
                raise RuntimeError(f'IFC validation failed for product #{product_id}.')
        for entity_id, serialized in original_entities.items():
            if check.by_id(entity_id).to_string() != serialized:
                raise RuntimeError(f'IFC metadata/geometry changed for entity #{entity_id}.')
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'products_validated': len(before), 'root_placements': len(roots), 'metres_per_unit': scale}
