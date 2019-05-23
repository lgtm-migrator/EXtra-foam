"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

ImageToolWindow.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
import os.path as osp
import functools

from ..pyqtgraph import QtCore, QtGui

from .base_window import AbstractWindow, SingletonWindow
from ..mediator import Mediator
from ..plot_widgets import ImageAnalysis
from ..misc_widgets import SmartLineEdit, SmartBoundaryLineEdit
from ...config import config, ImageMaskChange


class _RoiCtrlWidgetBase(QtGui.QWidget):
    """Base class for RoiCtrlWidget.

    Implemented four QLineEdits (x, y, w, h) and their connection to the
    corresponding ROI.
    """
    # (rank, x, y, w, h) where rank starts from 1
    roi_region_change_sgn = QtCore.Signal(object)
    # (rank, visible)
    roi_visibility_change_sgn = QtCore.Signal(object)

    _pos_validator = QtGui.QIntValidator(-10000, 10000)
    _size_validator = QtGui.QIntValidator(1, 10000)

    def __init__(self, roi, *, parent=None):
        super().__init__(parent=parent)
        self._roi = roi

        self._width_le = SmartLineEdit()
        self._width_le.setValidator(self._size_validator)
        self._height_le = SmartLineEdit()
        self._height_le.setValidator(self._size_validator)
        self._px_le = SmartLineEdit()
        self._px_le.setValidator(self._pos_validator)
        self._py_le = SmartLineEdit()
        self._py_le.setValidator(self._pos_validator)
        self._width_le.returnPressed.connect(self.onRoiSizeEdited)
        self._height_le.returnPressed.connect(self.onRoiSizeEdited)
        self._px_le.returnPressed.connect(self.onRoiPositionEdited)
        self._py_le.returnPressed.connect(self.onRoiPositionEdited)

        self._line_edits = (self._width_le, self._height_le,
                            self._px_le, self._py_le)

        roi.sigRegionChangeFinished.connect(self.onRoiRegionChangeFinished)

    @QtCore.pyqtSlot()
    def onRoiPositionEdited(self):
        x, y = [int(v) for v in self._roi.pos()]
        w, h = [int(v) for v in self._roi.size()]

        if self.sender() == self._px_le:
            x = int(self._px_le.text())
        elif self.sender() == self._py_le:
            y = int(self._py_le.text())

        # If 'update' == False, the state change will be remembered
        # but not processed and no signals will be emitted.
        self._roi.setPos((x, y), update=False)
        # trigger sigRegionChanged which moves the handler(s)
        # finish=False -> sigRegionChangeFinished will not emit, which
        # otherwise triggers infinite recursion
        self._roi.stateChanged(finish=False)

        self.roi_region_change_sgn.emit((self._roi.rank, x, y, w, h))

    @QtCore.pyqtSlot()
    def onRoiSizeEdited(self):
        x, y = [int(v) for v in self._roi.pos()]
        w, h = [int(v) for v in self._roi.size()]
        if self.sender() == self._width_le:
            w = int(self._width_le.text())
        elif self.sender() == self._height_le:
            h = int(self._height_le.text())

        # If 'update' == False, the state change will be remembered
        # but not processed and no signals will be emitted.
        self._roi.setSize((w, h), update=False)
        # trigger sigRegionChanged which moves the handler(s)
        # finish=False -> sigRegionChangeFinished will not emit, which
        # otherwise triggers infinite recursion
        self._roi.stateChanged(finish=False)

        self.roi_region_change_sgn.emit((self._roi.rank, x, y, w, h))

    @QtCore.pyqtSlot(object)
    def onRoiRegionChangeFinished(self, roi):
        """Connect to the signal from an ROI object."""
        x, y = [int(v) for v in roi.pos()]
        w, h = [int(v) for v in roi.size()]
        self.updateParameters(x, y, w, h)
        # inform widgets outside this window
        self.roi_region_change_sgn.emit((self._roi.rank, x, y, w, h))

    def notifyRoiParams(self):
        # fill the QLineEdit(s)
        self._roi.sigRegionChangeFinished.emit(self._roi)

    def updateParameters(self, x, y, w, h):
        self.roi_region_change_sgn.disconnect()
        self._px_le.setText(str(x))
        self._py_le.setText(str(y))
        self._width_le.setText(str(w))
        self._height_le.setText(str(h))
        self.roi_region_change_sgn.connect(Mediator().onRoiRegionChange)

    def setEditable(self, editable):
        for w in self._line_edits:
            w.setDisabled(not editable)


class _SingleRoiCtrlWidget(_RoiCtrlWidgetBase):
    """Widget for controlling of a single ROI."""

    def __init__(self, roi, *, parent=None):
        """Initialization.

        :param RectROI roi: RectROI object.
        """
        super().__init__(roi, parent=parent)

        self.activate_cb = QtGui.QCheckBox("On")
        self.lock_cb = QtGui.QCheckBox("Lock")

        self.initUI()

        self.disableAllEdit()

        self.activate_cb.stateChanged.connect(self.onToggleRoiActivation)
        self.activate_cb.stateChanged.emit(self.activate_cb.checkState())
        self.lock_cb.stateChanged.connect(self.onLock)

    def initUI(self):
        layout = QtGui.QHBoxLayout()
        layout.addWidget(QtGui.QLabel(
            f"ROI{self._roi.rank} ({self._roi.color[0]}): "))
        layout.addWidget(self.activate_cb)
        layout.addWidget(self.lock_cb)
        layout.addWidget(QtGui.QLabel("w: "))
        layout.addWidget(self._width_le)
        layout.addWidget(QtGui.QLabel("h: "))
        layout.addWidget(self._height_le)
        layout.addWidget(QtGui.QLabel("x: "))
        layout.addWidget(self._px_le)
        layout.addWidget(QtGui.QLabel("y: "))
        layout.addWidget(self._py_le)

        self.setLayout(layout)
        # left, top, right, bottom
        self.layout().setContentsMargins(2, 1, 2, 1)

    @QtCore.pyqtSlot(int)
    def onToggleRoiActivation(self, state):
        activated = state == QtCore.Qt.Checked
        if activated:
            self._roi.show()
            self.enableAllEdit()
        else:
            self._roi.hide()
            self.disableAllEdit()

        self.roi_visibility_change_sgn.emit((self._roi.rank, activated))

    @QtCore.pyqtSlot(int)
    def onLock(self, state):
        self._roi.setLocked(state == QtCore.Qt.Checked)
        self.setEditable(not state == QtCore.Qt.Checked)

    def disableAllEdit(self):
        self.setEditable(False)
        self.lock_cb.setDisabled(True)

    def enableAllEdit(self):
        self.lock_cb.setDisabled(False)
        self.setEditable(True)


class _RoiCtrlWidgetGroup(QtGui.QGroupBox):
    """Widget for controlling of a group of ROIs."""

    def __init__(self, rois, *, parent=None):
        super().__init__(parent)

        mediator = Mediator()

        self._roi_ctrls = []
        for roi in rois:
            widget = _SingleRoiCtrlWidget(roi)
            self._roi_ctrls.append(widget)
            widget.roi_region_change_sgn.connect(mediator.onRoiRegionChange)
            widget.roi_visibility_change_sgn.connect(
                mediator.onRoiVisibilityChange)
            widget.notifyRoiParams()

        self.initUI()

    def initUI(self):
        layout = QtGui.QGridLayout()
        for i, roi_ctrl in enumerate(self._roi_ctrls):
            layout.addWidget(roi_ctrl, i, 0, 1, 5)
        self.setLayout(layout)


class _ImageCtrlWidget(QtGui.QGroupBox):
    def __init__(self, *, parent=None):
        super().__init__(parent)

        self.update_image_btn = QtGui.QPushButton("Update image")
        self.auto_level_btn = QtGui.QPushButton("Auto level")
        self.set_ref_btn = QtGui.QPushButton("Set reference")
        self.remove_ref_btn = QtGui.QPushButton("Remove reference")

        self.initUI()

    def initUI(self):
        """Override."""
        layout = QtGui.QGridLayout()

        layout.addWidget(self.update_image_btn, 0, 0, 1, 2)
        layout.addWidget(self.auto_level_btn, 0, 2, 1, 2)
        layout.addWidget(self.set_ref_btn, 1, 0, 1, 2)
        layout.addWidget(self.remove_ref_btn, 1, 2, 1, 2)
        self.setLayout(layout)


class _ImageActionWidget(QtGui.QWidget):
    """Image ctrl widget in the action bar."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.moving_avg_le = SmartLineEdit(str(1))
        self.moving_avg_le.setValidator(QtGui.QIntValidator(1, 9999999))
        self.moving_avg_le.setMinimumWidth(60)

        self.threshold_mask_le = SmartBoundaryLineEdit(
            ', '.join([str(v) for v in config["MASK_RANGE"]]))
        # avoid collapse on online and maxwell clusters
        self.threshold_mask_le.setMinimumWidth(160)

        self.bkg_le = SmartLineEdit(str(0.0))
        self.bkg_le.setValidator(QtGui.QDoubleValidator())

        self.initUI()

        self.setFixedSize(self.minimumSizeHint())

    def initUI(self):
        layout = QtGui.QHBoxLayout()
        layout.addWidget(QtGui.QLabel("Moving average: "))
        layout.addWidget(self.moving_avg_le)
        layout.addWidget(QtGui.QLabel("Threshold mask: "))
        layout.addWidget(self.threshold_mask_le)
        layout.addWidget(QtGui.QLabel("Subtract background: "))
        layout.addWidget(self.bkg_le)

        self.setLayout(layout)
        self.layout().setContentsMargins(2, 1, 2, 1)


@SingletonWindow
class ImageToolWindow(AbstractWindow):
    """ImageToolWindow class.

    This is the second Main GUI which focuses on manipulating the image
    , e.g. selecting ROI, masking, cropping, normalization, for different
    data analysis scenarios.
    """

    title = "Image tool"

    _root_dir = osp.dirname(osp.abspath(__file__))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._image_view = ImageAnalysis(hide_axis=False, parent=self)

        # image ctrl widget in the toolbar

        self._tool_bar_image = self.addToolBar("image")

        self._image_action = _ImageActionWidget()
        self._image_action_at = QtGui.QWidgetAction(self._tool_bar_image)
        self._image_action_at.setDefaultWidget(self._image_action)
        self._tool_bar_image.addAction(self._image_action_at)

        # start another line of tool bar
        self.addToolBarBreak()

        # mask tool bar

        self._tool_bar_mask = self.addToolBar("mask")

        mask_at = self._addAction(self._tool_bar_mask, "Mask", "mask.png")
        mask_at.setCheckable(True)
        # Note: the sequence of the following two 'connect'
        mask_at.toggled.connect(self._exclude_actions)
        mask_at.toggled.connect(functools.partial(
            self._image_view.onDrawToggled, ImageMaskChange.MASK))

        unmask_at = self._addAction(
            self._tool_bar_mask, "Unmask", "un_mask.png")
        unmask_at.setCheckable(True)
        # Note: the sequence of the following two 'connect'
        unmask_at.toggled.connect(self._exclude_actions)
        unmask_at.toggled.connect(functools.partial(
            self._image_view.onDrawToggled, ImageMaskChange.UNMASK))

        clear_mask_at = self._addAction(
            self._tool_bar_mask, "Trash mask", "trash_mask.png")
        clear_mask_at.triggered.connect(self._image_view.onClearMask)

        save_img_mask_at = self._addAction(
            self._tool_bar_mask, "Save image mask", "save_mask.png")
        save_img_mask_at.triggered.connect(self._image_view.saveImageMask)

        load_img_mask_at = self._addAction(
            self._tool_bar_mask, "Load image mask", "load_mask.png")
        load_img_mask_at.triggered.connect(self._image_view.loadImageMask)

        # crop tool bar

        self._tool_bar_crop = self.addToolBar("crop")

        crop_at = self._addAction(
            self._tool_bar_crop, "Crop", "crop_selection.png")
        crop_at.setCheckable(True)
        crop_at.toggled.connect(self._exclude_actions)
        crop_at.toggled.connect(self._image_view.onCropToggle)

        crop_to_selection_at = self._addAction(
            self._tool_bar_crop, "Crop to selection", "crop.png")
        crop_to_selection_at.triggered.connect(
            self._image_view.onCropConfirmed)
        crop_to_selection_at.triggered.connect(functools.partial(
            crop_at.setChecked, False))

        restore_image_at = self._addAction(
            self._tool_bar_crop, "Restore image", "restore.png")
        restore_image_at.triggered.connect(self._image_view.onRestoreImage)

        self._exclusive_actions = {mask_at, unmask_at, crop_at}

        # ROI and Image ctrl widget

        self._roi_ctrl_widget = _RoiCtrlWidgetGroup(
            self._image_view.rois, parent=self)
        self._image_ctrl_widget = _ImageCtrlWidget(parent=self)

        self.initUI()
        self.initConnections()

        self.resize(800, 800)
        self.update()

    def initUI(self):
        """Override."""
        layout = QtGui.QGridLayout()
        layout.addWidget(self._image_view, 0, 0, 1, 3)
        layout.addWidget(self._roi_ctrl_widget, 1, 0, 1, 2)
        layout.addWidget(self._image_ctrl_widget, 1, 2, 1, 1)

        self._cw.setLayout(layout)
        self.layout().setContentsMargins(0, 0, 0, 0)

    def initConnections(self):
        mediator = self._mediator

        # signal-slot connections of child widgets should also be set here

        self._image_ctrl_widget.update_image_btn.clicked.connect(
            self.updateImage)

        self._image_ctrl_widget.set_ref_btn.clicked.connect(
            self._image_view.setImageRef)

        self._image_ctrl_widget.remove_ref_btn.clicked.connect(
            self._image_view.removeImageRef)

        self._image_ctrl_widget.auto_level_btn.clicked.connect(
            mediator.reset_image_level_sgn)

        self._image_action.moving_avg_le.value_changed_sgn.connect(
            lambda x: self._image_view.onMovingAverageWindowChange(int(x)))
        self._image_action.moving_avg_le.value_changed_sgn.connect(
            lambda x: mediator.onImageMaWindowChange(int(x)))

        self._image_action.threshold_mask_le.value_changed_sgn.connect(
            lambda x: self._image_view.onThresholdMaskChange(x))
        self._image_action.threshold_mask_le.value_changed_sgn.connect(
            lambda x: mediator.onImageThresholdMaskChange(x))

        self._image_action.bkg_le.value_changed_sgn.connect(
            lambda x: self._image_view.onBkgChange(float(x)))
        self._image_action.bkg_le.value_changed_sgn.connect(
            lambda x: mediator.onImageBackgroundChange(float(x)))

    def update(self):
        """Update widgets.

        This method is called by the main GUI.
        """
        # Always automatically get an image
        if self._image_view.image is not None:
            return

        self.updateImage(auto_range=True, auto_levels=True)

    def updateImage(self, **kwargs):
        """Update the current image.

        :param kwargs: forward to ImageView.setImage().

        It is only used for updating the image manually.
        """
        data = self._data.get()
        if data.image is None:
            return

        self._image_view.setImageData(data.image, **kwargs)

    @QtCore.pyqtSlot(bool)
    def _exclude_actions(self, checked):
        if checked:
            for at in self._exclusive_actions:
                if at != self.sender():
                    at.setChecked(False)

    def _addAction(self, tool_bar, description, filename):
        icon = QtGui.QIcon(osp.join(self._root_dir, "../icons/" + filename))
        action = QtGui.QAction(icon, description, self)
        tool_bar.addAction(action)
        return action
