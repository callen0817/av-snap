"""Canonical rigid transforms. All translations are in SI metres."""
import numpy as np


def rigid_matrix(matrix):
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Expected a finite 4 × 4 rigid transformation.')
    rotation = matrix[:3, :3]
    if (not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8)
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-7)
            or not np.isclose(np.linalg.det(rotation), 1, atol=1e-7)):
        raise ValueError('Transformation must be rigid: no scale, shear or reflection.')
    return matrix.copy()


def from_correspondences(source, target):
    source, target = np.asarray(source, float), np.asarray(target, float)
    if source.ndim != 2 or source.shape[1:] != (3,) or source.shape != target.shape or len(source) < 3:
        raise ValueError('Select at least three matching source and target points.')
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError('Control points must be finite.')
    a, b = source - source.mean(0), target - target.mean(0)
    if np.linalg.matrix_rank(a, tol=1e-8) < 2 or np.linalg.matrix_rank(b, tol=1e-8) < 2:
        raise ValueError('Control points must not be coincident or collinear.')
    u, _, vt = np.linalg.svd(a.T @ b)
    correction = np.eye(3)
    correction[2, 2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = target.mean(0) - rotation @ source.mean(0)
    return rigid_matrix(result)
