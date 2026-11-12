import tempfile
import unittest
from pathlib import Path
import numpy as np
import ifcopenshell
from ifcopenshell.util.placement import get_local_placement
from src.ifc_export import export_ifc


def placement(f, xyz, parent=None):
    axis = f.create_entity('IfcAxis2Placement3D', f.create_entity('IfcCartesianPoint', tuple(map(float, xyz))))
    return f.create_entity('IfcLocalPlacement', parent, axis)


def model(path, millimetres=False):
    f = ifcopenshell.file(schema='IFC4')
    unit = f.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix='MILLI' if millimetres else None, Name='METRE')
    f.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), UnitsInContext=f.create_entity('IfcUnitAssignment', [unit]))
    site = placement(f, [100, 200, 0])
    building = placement(f, [10, 20, 5], site)
    for index, p in enumerate([site, building, placement(f, [3, 4, 5], building), placement(f, [-50, 10, 20])]):
        f.create_entity('IfcBuildingElementProxy', GlobalId=ifcopenshell.guid.new(), Name=f'Product {index}', ObjectPlacement=p)
    f.write(str(path))
    return f


class IFCExportTests(unittest.TestCase):
    def test_nested_multiroot_and_units_preserve_all_entities(self):
        for mm in [False, True]:
            with self.subTest(mm=mm), tempfile.TemporaryDirectory() as directory:
                source, output = Path(directory)/'source.ifc', Path(directory)/'result.ifc'
                f = model(source, mm)
                original = source.read_bytes()
                t = np.eye(4)
                t[:3, :3] = [[0,-1,0],[1,0,0],[0,0,1]]
                t[:3, 3] = [2,3,4]
                report = export_ifc(source, output, t)
                self.assertEqual(report['products_validated'], 4)
                self.assertEqual(report['root_placements'], 2)
                check = ifcopenshell.open(str(output))
                unit = .001 if mm else 1
                for a, b in zip(f.by_type('IfcProduct'), check.by_type('IfcProduct')):
                    before, after = get_local_placement(a.ObjectPlacement), get_local_placement(b.ObjectPlacement)
                    before[:3, 3] *= unit
                    after[:3, 3] *= unit
                    np.testing.assert_allclose(after, t @ before, atol=1e-8)
                    self.assertEqual(a.GlobalId, b.GlobalId)
                self.assertEqual(source.read_bytes(), original)

    def test_rejects_overwrite_and_nonrigid_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.ifc'
            model(source)
            with self.assertRaises(ValueError):
                export_ifc(source, source, np.eye(4))
            t = np.eye(4); t[0,0] = 2
            output = Path(directory)/'bad.ifc'
            with self.assertRaises(ValueError):
                export_ifc(source, output, t)
            self.assertFalse(output.exists())

    def test_failed_validation_preserves_existing_destination(self):
        from unittest.mock import patch
        import src.ifc_export as exporter
        with tempfile.TemporaryDirectory() as d:
            source,output=Path(d)/'source.ifc',Path(d)/'existing.ifc'
            model(source); output.write_text('existing deliverable')
            original=exporter._products
            count=[0]
            def corrupt_check(f):
                products=original(f); count[0]+=1
                if count[0]==2:
                    first=next(iter(products)); products[first]=products[first].copy(); products[first][0,3]+=100
                return products
            with patch.object(exporter,'_products',side_effect=corrupt_check):
                with self.assertRaises(RuntimeError): exporter.export_ifc(source,output,np.eye(4))
            self.assertEqual(output.read_text(),'existing deliverable')
            self.assertEqual(list(Path(d).glob('.av-snap-*')),[])

    def test_ifc_geometry_extraction_uses_si_units_and_bounded_sampling(self):
        from src.io_manager import IOManager
        for mm in [False,True]:
            with self.subTest(mm=mm),tempfile.TemporaryDirectory() as d:
                path=Path(d)/'geometry.ifc'; f=model(path,mm)
                origin=f.create_entity('IfcAxis2Placement3D',f.create_entity('IfcCartesianPoint',(0.,0.,0.)))
                context=f.create_entity('IfcGeometricRepresentationContext',ContextIdentifier='Model',ContextType='Model',CoordinateSpaceDimension=3,Precision=1e-5,WorldCoordinateSystem=origin)
                f.by_type('IfcProject')[0].RepresentationContexts=[context]
                size=1000. if mm else 1.
                vertices=f.create_entity('IfcCartesianPointList3D',CoordList=[(0.,0.,0.),(size,0.,0.),(0.,size,0.),(0.,0.,size)])
                faces=[f.create_entity('IfcIndexedPolygonalFace',CoordIndex=idx) for idx in [(1,3,2),(1,2,4),(2,3,4),(3,1,4)]]
                solid=f.create_entity('IfcPolygonalFaceSet',Coordinates=vertices,Closed=True,Faces=faces)
                representation=f.create_entity('IfcShapeRepresentation',ContextOfItems=context,RepresentationIdentifier='Body',RepresentationType='Tessellation',Items=[solid])
                product=f.by_type('IfcProduct')[0]
                product.Representation=f.create_entity('IfcProductDefinitionShape',Representations=[representation])
                product.ObjectPlacement=placement(f,[0,0,0])
                f.write(str(path))
                io=IOManager(); cloud=io.load_dataset(str(path))
                self.assertLessEqual(len(cloud.points),250_000)
                self.assertLessEqual(max(cloud.get_max_bound()),1.001)
                self.assertGreater(max(cloud.get_max_bound()),.9)

    def test_georeferencing_metadata_is_preserved_without_reprojection(self):
        with tempfile.TemporaryDirectory() as d:
            source,output=Path(d)/'source.ifc',Path(d)/'out.ifc'; f=model(source)
            context=f.create_entity('IfcGeometricRepresentationContext',ContextType='Model',CoordinateSpaceDimension=3,Precision=1e-5,WorldCoordinateSystem=f.create_entity('IfcAxis2Placement3D',f.create_entity('IfcCartesianPoint',(0.,0.,0.))))
            crs=f.create_entity('IfcProjectedCRS',Name='EPSG:32618')
            conversion=f.create_entity('IfcMapConversion',SourceCRS=context,TargetCRS=crs,Eastings=500000.,Northings=4500000.,OrthogonalHeight=0.,XAxisAbscissa=1.,XAxisOrdinate=0.,Scale=1.)
            f.write(str(source)); t=np.eye(4); t[:3,3]=[1,2,3]
            export_ifc(source,output,t)
            check=ifcopenshell.open(str(output))
            self.assertEqual(check.by_type('IfcMapConversion')[0].to_string(),conversion.to_string())
