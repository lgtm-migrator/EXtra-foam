"""
Distributed under the terms of the BSD 3-Clause License.

The full license is in the file LICENSE, distributed with this software.

Author: Jun Zhu <jun.zhu@xfel.eu>, Ebad Kamil <ebad.kamil@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
from collections import OrderedDict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QGridLayout, QLabel

from .base_ctrl_widgets import _AbstractGroupBoxCtrlWidget
from .smart_widgets import SmartBoundaryLineEdit
from ...config import Normalizer


class Projection1DCtrlWidget(_AbstractGroupBoxCtrlWidget):
    """Widget for setting up ROI 1D projection analysis parameters."""

    _available_normalizers = OrderedDict({
        "": Normalizer.UNDEFINED,
        "AUC": Normalizer.AUC,
        "XGM": Normalizer.XGM,
        "ROI3 (sum)": Normalizer.ROI3,
        "ROI4 (sum)": Normalizer.ROI4,
        "ROI3 (sum) - ROI4 (sum)": Normalizer.ROI3_SUB_ROI4,
        "ROI3 (sum) + ROI4 (sum)": Normalizer.ROI3_ADD_ROI4,
    })

    def __init__(self, *args, **kwargs):
        super().__init__("ROI 1D projection setup", *args, **kwargs)

        self._direct_cb = QComboBox()
        for v in ['x', 'y']:
            self._direct_cb.addItem(v)

        self._normalizers_cb = QComboBox()
        for v in self._available_normalizers:
            self._normalizers_cb.addItem(v)

        self._auc_range_le = SmartBoundaryLineEdit("0, Inf")
        self._fom_integ_range_le = SmartBoundaryLineEdit("0, Inf")

        self.initUI()
        self.initConnections()

        self.setFixedHeight(self.minimumSizeHint().height())

    def initUI(self):
        """Overload."""
        layout = QGridLayout()
        AR = Qt.AlignRight

        layout.addWidget(QLabel("Direction: "), 0, 0, AR)
        layout.addWidget(self._direct_cb, 0, 1)
        layout.addWidget(QLabel("Normalizer: "), 1, 0, AR)
        layout.addWidget(self._normalizers_cb, 1, 1)
        layout.addWidget(QLabel("AUC range: "), 2, 0, AR)
        layout.addWidget(self._auc_range_le, 2, 1)
        layout.addWidget(QLabel("FOM range: "), 3, 0, AR)
        layout.addWidget(self._fom_integ_range_le, 3, 1)

        self.setLayout(layout)

    def initConnections(self):
        """Overload."""
        mediator = self._mediator

        self._direct_cb.currentTextChanged.connect(
            mediator.onRoiProjDirectChange)

        self._normalizers_cb.currentTextChanged.connect(
            lambda x: mediator.onRoiProjNormalizerChange(
                self._available_normalizers[x]))

        self._auc_range_le.value_changed_sgn.connect(
            mediator.onRoiProjAucRangeChange)

        self._fom_integ_range_le.value_changed_sgn.connect(
            mediator.onRoiProjFomIntegRangeChange)

    def updateMetaData(self):
        """Overload."""
        self._direct_cb.currentTextChanged.emit(
            self._direct_cb.currentText())

        self._normalizers_cb.currentTextChanged.emit(
            self._normalizers_cb.currentText())

        self._auc_range_le.returnPressed.emit()

        self._fom_integ_range_le.returnPressed.emit()

        return True