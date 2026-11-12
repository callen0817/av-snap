import tempfile
import unittest
from pathlib import Path
import numpy as np
from src.project import AlignmentProject,fingerprint


class ProjectTests(unittest.TestCase):
    def project(self,d):
        a,b=Path(d)/'a.ply',Path(d)/'b.ply'; a.write_text('anchor'); b.write_text('moving')
        return AlignmentProject(anchor=str(a),moving=str(b),report={'status':'Validated'},fingerprints={'anchor':fingerprint(a),'moving':fingerprint(b)})

    def test_approval_lock_invalidation_undo_redo_restore(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.project(d)
            p.approve(); p.require_export()
            path=Path(d)/'session.avsnap'; p.save(path)
            restored=AlignmentProject.load(path)
            self.assertFalse(restored.approved); self.assertFalse(restored.report)
            with self.assertRaises(ValueError): restored.require_export()
            t=np.eye(4); t[0,3]=1
            p.set_transform(t,{'status':'Validated'})
            self.assertFalse(p.approved)
            self.assertTrue(p.undo()); np.testing.assert_allclose(p.matrix,np.eye(4))
            self.assertTrue(p.redo()); np.testing.assert_allclose(p.matrix,t)
            self.assertFalse(p.report)

    def test_failed_uncertain_and_changed_sources(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.project(d); p.report={'status':'Failed'}
            with self.assertRaises(ValueError): p.approve('override')
            p.report={'status':'Needs Review'}
            with self.assertRaises(ValueError): p.approve()
            p.approve('Reviewed control points against drawing'); p.require_export()
            Path(p.moving).write_text('modified')
            with self.assertRaises(ValueError): p.require_export()
            self.assertFalse(p.approved)
