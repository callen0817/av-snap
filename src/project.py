"""Review state and portable, atomic project files. Restores never imply approval."""
import json
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np
from src.transforms import rigid_matrix


def fingerprint(path):
    stat=Path(path).stat()
    return {'path':str(Path(path).resolve()),'size':stat.st_size,'modified_ns':stat.st_mtime_ns}


def atomic_json(path, data):
    fd, temp=tempfile.mkstemp(prefix='.av-snap-',suffix='.json',dir=Path(path).resolve().parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(data,stream,indent=2,allow_nan=False)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


@dataclass
class AlignmentProject:
    anchor: str = ''
    moving: str = ''
    matrix: np.ndarray = field(default_factory=lambda:np.eye(4))
    report: dict = field(default_factory=dict)
    approved: bool = False
    approval_note: str = ''
    history: list = field(default_factory=list)
    future: list = field(default_factory=list)
    fingerprints: dict = field(default_factory=dict)

    def set_transform(self, matrix, report):
        self.history.append(self.matrix.copy()); self.future.clear()
        self.matrix=rigid_matrix(matrix); self.report=report
        self.revoke()

    def revoke(self):
        self.approved=False; self.approval_note=''

    def approve(self, note=''):
        self.verify_sources()
        status=self.report.get('status','Failed')
        if status not in {'Validated','Needs Review'}: raise ValueError('Failed or unvalidated alignment cannot be approved.')
        if status != 'Validated' and not note.strip():
            raise ValueError('An explicit review note is required for uncertain alignment.')
        self.approved=True; self.approval_note=note.strip()

    def verify_sources(self):
        for key,path in [('anchor',self.anchor),('moving',self.moving)]:
            if key not in self.fingerprints or fingerprint(path)!=self.fingerprints[key]:
                self.revoke()
                raise ValueError('Source files changed or were not fingerprinted; reload and realign before export.')

    def require_export(self):
        self.verify_sources()
        if not self.approved or self.report.get('status','Failed') == 'Failed':
            raise ValueError('Review and approve a successful alignment before export.')

    def undo(self):
        if not self.history: return False
        self.future.append(self.matrix.copy()); self.matrix=self.history.pop(); self.report={}; self.revoke()
        return True

    def redo(self):
        if not self.future: return False
        self.history.append(self.matrix.copy()); self.matrix=self.future.pop(); self.report={}; self.revoke()
        return True

    def to_dict(self):
        return {'schema_version':1,'anchor':self.anchor,'moving':self.moving,'matrix':self.matrix.tolist(),
                'report':self.report,'approved':self.approved,'approval_note':self.approval_note,
                'fingerprints':self.fingerprints,'coordinate_frame':'local engineering coordinates','translation_units':'metres'}

    def save(self,path):
        atomic_json(path,self.to_dict())

    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('schema_version')!=1: raise ValueError('Unsupported project version.')
        project=cls(anchor=data['anchor'],moving=data['moving'],matrix=rigid_matrix(data['matrix']),fingerprints=data.get('fingerprints',{}))
        project.verify_sources()
        # QA and approval are always recomputed from actual geometry on restore.
        return project
