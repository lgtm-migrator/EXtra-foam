"""
Distributed under the terms of the BSD 3-Clause License.

The full license is in the file LICENSE, distributed with this software.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
import warnings

import numpy as np

from PyQt5.QtGui import QPainter
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt5.QtWidgets import (
    QCheckBox, QGraphicsGridLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy,
    QSlider, QWidget, QWidgetAction
)

from .. import pyqtgraph as pg
from ..pyqtgraph import Point
from ..pyqtgraph import functions as fn


class HistogramLUTItem(pg.GraphicsWidget):
    """GraphicsWidget for adjusting the display of an image.

    Implemented based on pyqtgraph.HistogramLUTItem.
    """

    lut_changed_sgn = pyqtSignal(object)

    def __init__(self, image_item, parent=None):
        super().__init__(parent=parent)
        self._lut = None

        gradient = pg.GradientEditorItem()
        gradient.setOrientation('right')
        gradient.loadPreset('grey')
        self._gradient = gradient
        self._gradient.show()

        lri = pg.LinearRegionItem([0, 1], 'horizontal', swapMode='block')
        lri.setZValue(1000)
        lri.lines[0].addMarker('<|', 0.5)
        lri.lines[1].addMarker('|>', 0.5)
        self._lri = lri

        self._hist = pg.PlotCurveItem(pen=(0, 0, 0, 255))
        self._hist.rotate(90)

        vb = pg.ViewBox(parent=self)
        vb.setMaximumWidth(152)
        vb.setMinimumWidth(45)
        vb.setMouseEnabled(x=False, y=True)
        vb.addItem(self._hist)
        vb.addItem(self._lri)
        vb.enableAutoRange(pg.ViewBox.XYAxes)
        self._vb = vb

        self._axis = pg.AxisItem(
            'left', linkView=self._vb, maxTickLength=-10, parent=self)

        self.initUI()
        self.initConnections()

        image_item.image_changed_sgn.connect(self.onImageChanged)
        # send function pointer, not the result
        image_item.setLookupTable(self.getLookupTable)
        self._image_item = image_item
        # If image_item._image is None, the following line does not initialize
        # image_item._levels
        self.onImageChanged(auto_levels=True)
        # synchronize levels
        image_item.setLevels(self.getLevels())

    def initUI(self):
        layout = QGraphicsGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addItem(self._axis, 0, 0)
        layout.addItem(self._vb, 0, 1)
        layout.addItem(self._gradient, 0, 2)
        self.setLayout(layout)

    def initConnections(self):
        self._lri.sigRegionChanged.connect(self.regionChanging)
        self._lri.sigRegionChangeFinished.connect(self.regionChanged)

        self._gradient.sigGradientChanged.connect(self.gradientChanged)

        self._vb.sigRangeChanged.connect(self.update)

    def paint(self, p, *args):
        """Override."""
        pen = self._lri.lines[0].pen
        rgn = self.getLevels()
        p1 = self._vb.mapFromViewToItem(
            self, Point(self._vb.viewRect().center().x(), rgn[0]))
        p2 = self._vb.mapFromViewToItem(
            self, Point(self._vb.viewRect().center().x(), rgn[1]))

        rect = self._gradient.mapRectToParent(self._gradient.gradRect.rect())
        p.setRenderHint(QPainter.Antialiasing)

        for pen in [fn.mkPen((0, 0, 0, 100), width=3), pen]:
            p.setPen(pen)
            p.drawLine(p1 + Point(0, 5), rect.bottomLeft())
            p.drawLine(p2 - Point(0, 5), rect.topLeft())
            p.drawLine(rect.topLeft(), rect.topRight())
            p.drawLine(rect.bottomLeft(), rect.bottomRight())

    def gradientChanged(self):
        if self._gradient.isLookupTrivial():
            # lambda x: x.astype(np.uint8))
            self._image_item.setLookupTable(None)
        else:
            # send function pointer, not the result
            self._image_item.setLookupTable(self.getLookupTable)

        self._lut = None
        self.lut_changed_sgn.emit(self)

    def getLookupTable(self, img=None, n=None, alpha=None):
        """Return the look-up table."""
        if self._lut is None:
            if n is None:
                n = 256 if img.dtype == np.uint8 else 512
            self._lut = self._gradient.getLookupTable(n, alpha=alpha)
        return self._lut

    def regionChanging(self):
        """One line of the region is being dragged."""
        self._image_item.setLevels(self.getLevels())
        self.update()

    def regionChanged(self):
        """Line dragging has finished."""
        self._image_item.setLevels(self.getLevels())

    def onImageChanged(self, auto_levels=False):
        hist, bin_centers = self._image_item.histogram()

        if hist is None:
            self._hist.setData([], [])
            return

        self._hist.setData(bin_centers, hist)
        if auto_levels:
            self._lri.setRegion((bin_centers[0], bin_centers[-1]))
        else:
            # synchronize levels if ImageItem updated its image with
            # auto_levels = True
            self._lri.setRegion(self._image_item.getLevels())

    def setColorMap(self, cm):
        self._gradient.setColorMap(cm)

    def getLevels(self):
        return self._lri.getRegion()

    def setLevels(self, levels):
        """Called by HistogramLUTItem."""
        self._lri.setRegion(levels)


class PlotArea(pg.GraphicsWidget):
    """GraphicsWidget implementing a standard 2D plotting area with axes.

    Implemented based on pyqtgraph.PlotItem.

    It has the following functionalities:

    - Manage placement of a ViewBox, AxisItems, and LabelItems;
    - Manage a list of GraphicsItems displayed inside the ViewBox;
    - Implement a context menu with display options.
    """
    # Emitted when the ViewBox range has changed
    range_changed_sgn = pyqtSignal(object, object)
    # Emitted when the ViewBox Y range has changed
    sigYRangeChanged = pyqtSignal(object, object)
    # Emitted when the ViewBox X range has changed
    sigXRangeChanged = pyqtSignal(object, object)

    def __init__(self, name=None, parent=None):
        super().__init__(parent=parent)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._items = set()

        self._vb = pg.ViewBox(parent=self)

        if name is not None:
            self._vb.register(name)

        self._legend = None
        self._axes = {}
        self._title = pg.LabelItem('', size='11pt', parent=self)

        # context menu
        self._show_x_grid_cb = QCheckBox("Show X Grid")
        self._show_y_grid_cb = QCheckBox("Show Y Grid")
        self._grid_opacity_sld = QSlider(Qt.Horizontal)
        self._grid_opacity_sld.setMinimum(0)
        self._grid_opacity_sld.setMaximum(255)
        self._grid_opacity_sld.setValue(160)
        self._grid_opacity_sld.setSingleStep(1)
        self._menu = None

        self._layout = QGraphicsGridLayout()

        self.initUI()
        self.initConnections()

    def initUI(self):
        layout = self._layout

        layout.setContentsMargins(1, 1, 1, 1)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)

        layout.addItem(self._title, 0, 1)
        layout.addItem(self._vb, 2, 1)

        self._initAxisItems()
        self.setTitle()

        for i in range(4):
            layout.setRowPreferredHeight(i, 0)
            layout.setRowMinimumHeight(i, 0)
            layout.setRowSpacing(i, 0)
            layout.setRowStretchFactor(i, 1)

        for i in range(3):
            layout.setColumnPreferredWidth(i, 0)
            layout.setColumnMinimumWidth(i, 0)
            layout.setColumnSpacing(i, 0)
            layout.setColumnStretchFactor(i, 1)

        layout.setRowStretchFactor(2, 100)
        layout.setColumnStretchFactor(1, 100)

        self.setLayout(layout)

        self._initContextMenu()

    def initConnections(self):
        self._vb.sigRangeChanged.connect(self.range_changed_sgn)
        self._vb.sigXRangeChanged.connect(self.sigXRangeChanged)
        self._vb.sigYRangeChanged.connect(self.sigYRangeChanged)

        self._show_x_grid_cb.toggled.connect(self._onShowGridChanged)
        self._show_y_grid_cb.toggled.connect(self._onShowGridChanged)
        self._grid_opacity_sld.sliderReleased.connect(self._onShowGridChanged)

    def _initContextMenu(self):
        self._menu = [
            QMenu("Grid"),
        ]

        grid_menu = self._menu[0]
        show_x_act = QWidgetAction(grid_menu)
        show_x_act.setDefaultWidget(self._show_x_grid_cb)
        grid_menu.addAction(show_x_act)
        show_y_act = QWidgetAction(grid_menu)
        show_y_act.setDefaultWidget(self._show_y_grid_cb)
        grid_menu.addAction(show_y_act)
        opacity_act = QWidgetAction(grid_menu)
        widget = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Opacity"))
        layout.addWidget(self._grid_opacity_sld)
        widget.setLayout(layout)
        opacity_act.setDefaultWidget(widget)
        grid_menu.addAction(opacity_act)

    def _initAxisItems(self):
        for orient, pos in (('top', (1, 1)),
                            ('bottom', (3, 1)),
                            ('left', (2, 0)),
                            ('right', (2, 2))):
            axis = pg.AxisItem(orientation=orient, parent=self)

            axis.linkToView(self._vb)
            self._axes[orient] = {'item': axis, 'pos': pos}
            self._layout.addItem(axis, *pos)
            axis.setZValue(-1000)
            axis.setFlag(axis.ItemNegativeZStacksBehindParent)

            self.showAxis(orient, orient in ['left', 'bottom'])

    def getViewBox(self):
        return self._vb

    @pyqtSlot()
    def _onShowGridChanged(self):
        alpha = self._grid_opacity_sld.value()
        x = alpha if self._show_x_grid_cb.isChecked() else False
        y = alpha if self._show_y_grid_cb.isChecked() else False
        self.getAxis('bottom').setGrid(x)
        self.getAxis('left').setGrid(y)

    def addItem(self, item, ignore_bounds=False):
        """Add a plot item to ViewBox."""
        if item in self._items:
            warnings.warn(f'Item {item} already added to PlotItem, ignoring.')
            return

        self._items.add(item)
        self._vb.addItem(item, ignoreBounds=ignore_bounds)
        if self._legend is not None and isinstance(item, pg.PlotItem):
            self._legend.addItem(item, item.name())

    def removeItem(self, item):
        """Add a plot item to ViewBox."""
        if item not in self._items:
            return

        self._items.remove(item)
        self._vb.removeItem(item)
        if self._legend is not None:
            self._legend.removeItem(item)

    def removeAllItems(self):
        """Remove all plot items from the ViewBox."""
        for item in self._items:
            self._vb.removeItem(item)
            if self._legend is not None:
                self._legend.removeItem(item)
        self._items.clear()

    def getContextMenus(self, event):
        """Override."""
        return self._menu

    def getAxis(self, axis):
        """Return the specified AxisItem.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        """
        return self._axes[axis]['item']

    def showAxis(self, axis, show=True):
        """Show or hide the given axis.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param bool show: whether to show the axis.
        """
        s = self.getAxis(axis)
        if show:
            s.show()
        else:
            s.hide()

    def addLegend(self, offset=(30, 30), **kwargs):
        """Add a LegendItem if it does not exist."""
        if self._legend is None:
            self._legend = pg.LegendItem(offset=offset, pen='k', **kwargs)
            self._legend.setParentItem(self._vb)
        return self._legend

    def setLabel(self, axis, text=None, units=None, **args):
        """Set the label for an axis. Basic HTML formatting is allowed.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param str text: text to display along the axis. HTML allowed.
        """
        self.getAxis(axis).setLabel(text=text, units=units, **args)
        self.showAxis(axis)

    def showLabel(self, axis, show=True):
        """Show or hide one of the axis labels.

        :param str axis: one of 'left', 'bottom', 'right', or 'top'.
        :param bool show: whether to show the label.
        """
        self.getAxis(axis).showLabel(show)

    def setTitle(self, title=None, **args):
        """Set the title of the plot.

        :param str title: text to display along the axis. HTML allowed.
        """
        if title is None:
            self._title.setMaximumHeight(0)
            self._layout.setRowFixedHeight(0, 0)
            self._title.setVisible(False)
        else:
            self._title.setMaximumHeight(30)
            self._layout.setRowFixedHeight(0, 30)
            self._title.setText(title, **args)
            self._title.setVisible(True)

    def setAspectLocked(self, *args, **kwargs):
        self._vb.setAspectLocked(*args, **kwargs)

    def invertY(self, *args, **kwargs):
        self._vb.invertY(*args, **kwargs)

    def invertX(self, *args, **kwargs):
        self._vb.invertX(*args, **kwargs)
