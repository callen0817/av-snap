"""Independent, bidirectional geometric validation; scores are not probabilities."""
from dataclasses import dataclass, asdict, field
import copy
import numpy as np
import open3d as o3d
from src.transforms import rigid_matrix


@dataclass
class QualityReport:
    status: str
    source_overlap: float
    target_overlap: float
    median_residual_m: float
    p95_residual_m: float
    threshold_m: float
    score: float
    issues: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    elapsed_seconds: float = 0
    rss_mb_at_completion: float = 0

    def to_dict(self):
        return asdict(self)


def validate_alignment(source, target, matrix, threshold, max_samples=20_000):
    rigid_matrix(matrix)
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('Validation distance must be positive.')
    def sample(pcd):
        if len(pcd.points) > max_samples:
            return pcd.select_by_index(np.linspace(0,len(pcd.points)-1,max_samples,dtype=int).tolist())
        return copy.deepcopy(pcd)
    a, b = sample(source), sample(target)
    a.transform(matrix)
    if min(len(a.points),len(b.points)) < 6:
        raise ValueError('At least six points are required for independent validation.')
    da, db = np.asarray(a.compute_point_cloud_distance(b)), np.asarray(b.compute_point_cloud_distance(a))
    forward, reverse = float(np.mean(da <= threshold)), float(np.mean(db <= threshold))
    residuals = np.concatenate([da[da <= threshold], db[db <= threshold]])
    median, p95 = (float(np.median(residuals)), float(np.quantile(residuals,.95))) if len(residuals) else (float(threshold*10),float(threshold*10))
    score = 2 * forward * reverse / max(forward+reverse, 1e-12)
    issues = []
    status = 'Validated'
    if min(forward,reverse) < .15:
        status = 'Failed'; issues.append('Insufficient bidirectional overlap.')
    elif forward < .65 or reverse < .35 or p95 > threshold*.9:
        status = 'Needs Review'; issues.append('Partial overlap or residuals require review.')
    for cloud in [a,b]:
        eigenvalues = np.linalg.eigvalsh(np.cov(np.asarray(cloud.points).T))
        if eigenvalues[0] < max(eigenvalues[-1],1e-12)*1e-4:
            if status != 'Failed': status = 'Needs Review'
            issues.append('Planar or linear geometry does not independently constrain all motion.')
            break
    return QualityReport(status,forward,reverse,median,p95,float(threshold),score,issues)
