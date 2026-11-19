"""Bounded GPU point-cloud preview, independent of full-density exports."""
import os
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSlider,QCheckBox


class CloudViewport(QWidget):
    def __init__(self):
        super().__init__()
        self.anchor=None; self.moving=None; self.matrix=np.eye(4); self.items=[]; self.gl=None
        self._sample_cache={}
        self._error_cache={}
        self.layout=QVBoxLayout(self); self.layout.setContentsMargins(0,0,0,0)
        controls=QHBoxLayout()
        self.mode=QComboBox(); self.mode.addItems(['Aligned overlay','Original overlay','Color by error'])
        self.camera=QComboBox(); self.camera.addItems(['Perspective','Top','Front','Side'])
        self.anchor_toggle=QCheckBox('Anchor'); self.anchor_toggle.setChecked(True)
        self.moving_toggle=QCheckBox('Moving'); self.moving_toggle.setChecked(True)
        for widget in [self.mode,self.camera,self.anchor_toggle,self.moving_toggle]: controls.addWidget(widget)
        self.layout.addLayout(controls)
        self.message=QLabel('Import an anchor and moving dataset to begin.\nPreview is limited to 100,000 points per dataset; exports retain source density.')
        self.message.setAlignment(Qt.AlignCenter); self.message.setWordWrap(True)
        self.layout.addWidget(self.message,1)
        self.clip=QComboBox(); self.clip.addItems(['No section','Section X','Section Y','Section Z'])
        self.slice=QSlider(Qt.Horizontal); self.slice.setRange(0,100); self.slice.setValue(100)
        self.opacity=QSlider(Qt.Horizontal); self.opacity.setRange(10,100); self.opacity.setValue(85)
        bottom=QHBoxLayout(); bottom.addWidget(self.clip); bottom.addWidget(self.slice)
        bottom.addWidget(QLabel('Moving opacity')); bottom.addWidget(self.opacity)
        self.layout.addLayout(bottom)
        self.mode.currentIndexChanged.connect(self.render)
        self.camera.currentIndexChanged.connect(self.set_camera)
        self.anchor_toggle.toggled.connect(self.render); self.moving_toggle.toggled.connect(self.render)
        self.clip.currentIndexChanged.connect(self.render); self.slice.valueChanged.connect(self.render)
        self.opacity.valueChanged.connect(self.render)

    def initialize_gl(self):
        if self.gl is not None or os.environ.get('AV_SNAP_HEADLESS')=='1': return
        try:
            import pyqtgraph.opengl as gl
            self.gl_module=gl
            self.gl=gl.GLViewWidget(); self.gl.setBackgroundColor('#171a21')
            self.layout.insertWidget(1,self.gl,1); self.message.hide()
            grid=gl.GLGridItem(); grid.setSize(20,20); grid.setSpacing(1,1); self.gl.addItem(grid)
        except Exception as error:
            self.gl=None
            self.message.setText(f'3D preview unavailable ({error}).\nAlignment and export still work normally.')
            self.message.show()

    def clear_caches(self):
        self._sample_cache.clear()
        self._error_cache.clear()

    def _sampled_cloud(self, cloud, limit=100_000):
        key=(id(cloud), len(cloud.points), limit)
        cached=self._sample_cache.get(key)
        if cached is not None:
            return cached
        n=len(cloud.points)
        if n==0:
            result=(np.empty((0,3),dtype=float), None)
        else:
            ids=np.linspace(0,n-1,min(n,limit),dtype=int)
            pts=np.asarray(cloud.points)[ids].copy()
            cols=np.asarray(cloud.colors)[ids].copy() if cloud.has_colors() else None
            result=(pts, cols)
        self._sample_cache[key]=result
        return result

    def _error_colors(self, moving_points):
        matrix_key=self.matrix.tobytes() if self.mode.currentIndex()!=1 else b'orig'
        key=(id(self.anchor), id(self.moving), matrix_key, len(moving_points))
        cached=self._error_cache.get(key)
        if cached is not None:
            return cached
        from scipy.spatial import cKDTree
        reference,_=self._sampled_cloud(self.anchor, limit=200_000)
        distance,_=cKDTree(reference).query(moving_points)
        scale=max(float(np.quantile(distance,.95)),.001)
        value=np.clip(distance/scale,0,1)
        rgb=np.column_stack([value,1-value,.2*np.ones(len(value))])
        self._error_cache.clear()
        self._error_cache[key]=rgb
        return rgb

    def compute_section_bound(self, anchor_points, moving_points):
        if not self.clip.currentIndex():
            return None
        axis=self.clip.currentIndex()-1
        coords=[pts[:,axis] for pts in (anchor_points, moving_points) if len(pts)]
        if not coords:
            return None
        combined=np.concatenate(coords)
        lo=float(combined.min())
        span=float(np.ptp(combined))
        return lo + span * self.slice.value() / 100.0

    def set_clouds(self,anchor,moving,matrix):
        datasets_changed=(anchor is not self.anchor or moving is not self.moving)
        if datasets_changed:
            self.clear_caches()
        self.anchor,self.moving,self.matrix=anchor,moving,np.asarray(matrix).copy()
        self.initialize_gl(); self.render()
        if datasets_changed:
            self.set_camera()

    def render(self,*args):
        if self.anchor is None or self.moving is None: return
        if self.gl is None:
            self.message.setText('Headless preview: geometry loaded. Interactive 3D requires a desktop/OpenGL display.')
            return
        for item in self.items: self.gl.removeItem(item)
        self.items=[]
        center=np.asarray(self.anchor.get_center())
        anchor_pts, anchor_cols=self._sampled_cloud(self.anchor)
        moving_raw, moving_cols=self._sampled_cloud(self.moving)
        if len(moving_raw) and self.mode.currentIndex()!=1:
            moving_pts=moving_raw@self.matrix[:3,:3].T+self.matrix[:3,3]
        else:
            moving_pts=moving_raw
        bound=self.compute_section_bound(anchor_pts, moving_pts)
        axis=self.clip.currentIndex()-1
        datasets=[(anchor_pts, anchor_cols), (moving_pts, moving_cols)]
        for index,(points,raw_colors) in enumerate(datasets):
            if not [self.anchor_toggle,self.moving_toggle][index].isChecked(): continue
            if len(points)==0: continue
            colors=np.tile([.72,.74,.78,1] if not index else [.9,.76,.45,self.opacity.value()/100],(len(points),1))
            if raw_colors is not None and self.mode.currentIndex()!=2:
                colors[:,:3]=raw_colors
            if index and self.mode.currentIndex()==2:
                colors[:,:3]=self._error_colors(points)
            if bound is not None:
                mask=points[:,axis]<=bound
                if not np.any(mask):
                    continue
                points,colors=points[mask],colors[mask]
            item=self.gl_module.GLScatterPlotItem(pos=points-center,color=colors,size=2,pxMode=True)
            from OpenGL import GL
            item.setGLOptions('translucent'); item.updateGLOptions({'glDepthFunc':(GL.GL_LEQUAL,)})
            self.gl.addItem(item); self.items.append(item)

    def set_camera(self,*args):
        if self.gl is None or self.anchor is None: return
        distance=max(self.anchor.get_axis_aligned_bounding_box().get_extent())*1.7
        elevation,azimuth=[(30,45),(90,0),(0,0),(0,90)][self.camera.currentIndex()]
        self.gl.setCameraPosition(distance=max(distance,1),elevation=elevation,azimuth=azimuth)
