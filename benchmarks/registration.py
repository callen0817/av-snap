"""Reproducible synthetic registration benchmark, with optional old source root.

python benchmarks/registration.py --baseline /path/to/original --output benchmarks/results.json
Each case uses a fresh process and identical thread limits. No customer data.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def child(root,case):
    import time
    import threading
    import psutil
    import numpy as np
    import open3d as o3d
    sys.path.insert(0,root)
    from src.alignment_engine import AlignmentEngine
    rng=np.random.default_rng(42)
    points=rng.uniform([0,0,0],[3,2,1],(3000,3))
    angles=[0,0,0] if case=='translation' else [.08,-.06,.2]
    rotation=o3d.geometry.get_rotation_matrix_from_xyz(angles)
    offset=np.array([.3,-.2,.1])
    target=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    source=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points@rotation.T+offset))
    peak=[0]; stop=threading.Event()
    def monitor():
        while not stop.wait(.01): peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    monitor_thread=threading.Thread(target=monitor); monitor_thread.start()
    start=time.perf_counter()
    engine=AlignmentEngine()
    try:
        aligned,matrix=engine.execute_alignment(source,target)
        elapsed=time.perf_counter()-start
    finally:
        stop.set(); monitor_thread.join()
    rotation_error=np.degrees(np.arccos(np.clip((np.trace(matrix[:3,:3].T@rotation.T)-1)/2,-1,1)))
    translation_error=np.linalg.norm(matrix[:3,3]-(-rotation.T@offset))
    return {'case':case,'points':len(points),'seconds':elapsed,'peak_sampled_rss_mb':peak[0]/1024**2,
            'mean_distance_m':float(np.mean(aligned.compute_point_cloud_distance(target))),
            'rotation_error_degrees':float(rotation_error),'translation_error_m':float(translation_error),
            'status':getattr(getattr(engine,'last_report',None),'status','not independently validated')}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--baseline'); parser.add_argument('--output',default='benchmarks/results.json')
    parser.add_argument('--child',nargs=2); args=parser.parse_args()
    if args.child:
        print('RESULT_JSON='+json.dumps(child(*args.child))); return
    roots={'current':str(Path(__file__).resolve().parents[1])}
    if args.baseline: roots['baseline']=str(Path(args.baseline).resolve())
    results={'dataset':'Synthetic uniform 3 × 2 × 1 m volume, seed 42, 3000 points. Not a real-building quality benchmark.',
             'threads':2,'runs':[]}
    for version,root in roots.items():
        for case in ['translation','tilted_rigid']:
            environment=os.environ.copy(); environment.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
            run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',root,case],capture_output=True,text=True,env=environment,timeout=120)
            if run.returncode: raise RuntimeError(run.stderr)
            data=json.loads(next(line.removeprefix('RESULT_JSON=') for line in run.stdout.splitlines() if line.startswith('RESULT_JSON=')))
            results['runs'].append({'version':version,**data})
    Path(args.output).write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__': main()
