"""Open3D point-picking in its own process and main thread."""
import json
import sys
import numpy as np
import open3d as o3d
from src.alignment_engine import AlignmentEngine


def main(args=None):
    args=sys.argv[1:] if args is None else args
    source=o3d.io.read_point_cloud(args[0]); target=o3d.io.read_point_cloud(args[1])
    engine=AlignmentEngine()
    _,matrix=engine.execute_manual_alignment(source,target)
    np.save(args[2],matrix)
    with open(args[3],'w',encoding='utf-8') as stream:
        json.dump(engine.last_report.to_dict(),stream,allow_nan=False)

if __name__=='__main__': main()
