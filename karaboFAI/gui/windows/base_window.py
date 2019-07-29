"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Hold base classes for windows.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
from weakref import WeakKeyDictionary

from PyQt5 import QtGui

from ..pyqtgraph.dockarea import DockArea

from ..mediator import Mediator


class AbstractWindow(QtGui.QMainWindow):
    """Base class for various stand-alone windows.

    All the stand-alone windows should follow the interface defined
    in this abstract class.
    """
    title = ""

    def __init__(self, data=None, *, pulse_resolved=True, parent=None):
        """Initialization.

        :param Data4Visualization data: the data shared by widgets
            and windows.
        :param bool pulse_resolved: whether the related data is
            pulse-resolved or not.
        """
        super().__init__(parent=parent)
        if parent is not None:
            parent.registerWindow(self)

        self._mediator = Mediator()

        self._data = data
        self._pulse_resolved = pulse_resolved

        try:
            if self.title:
                title = parent.title + " - " + self.title
            else:
                title = parent.title

            self.setWindowTitle(title)
        except AttributeError:
            # for unit test where parent is None
            self.setWindowTitle(self.title)

        self._cw = QtGui.QWidget()
        self.setCentralWidget(self._cw)

        self.show()

    def initUI(self):
        """Initialization of UI.

        This method should call 'initCtrlUI' and 'initPlotUI'.
        """
        pass

    def initCtrlUI(self):
        """Initialization of ctrl UI.

        Initialization of the ctrl UI should take place in this method.
        """
        pass

    def initPlotUI(self):
        """Initialization of plot UI.

        Initialization of the plot UI should take place in this method.
        """
        pass

    def initConnections(self):
        """Initialization of signal-slot connections."""
        pass

    def updateMetaData(self):
        """Update metadata affected by this window."""
        return True

    def reset(self):
        """Reset data in widgets.

        This method is called by the main GUI.
        """
        pass

    def update(self):
        """Update widgets.

        This method is called by the main GUI.
        """
        pass

    def closeEvent(self, QCloseEvent):
        parent = self.parent()
        if parent is not None:
            parent.unregisterWindow(self)
        super().closeEvent(QCloseEvent)


class DockerWindow(AbstractWindow):
    """QMainWindow displaying a single DockArea."""
    def __init__(self, *args, **kwargs):
        """Initialization."""
        super().__init__(*args, **kwargs)

        self._plot_widgets = WeakKeyDictionary()  # book-keeping opened windows

        self._docker_area = DockArea()

    def initUI(self):
        """Override."""
        self.initPlotUI()
        layout = QtGui.QHBoxLayout()
        layout.addWidget(self._docker_area)
        layout.setContentsMargins(0, 0, 0, 0)
        self._cw.setLayout(layout)

    def update(self):
        """Update widgets.

        This method is called by the main GUI.
        """
        if self._data is None:
            return

        data = self._data.get()
        if data is None:
            return

        for widget in self._plot_widgets:
            widget.update(data)

    def reset(self):
        """Reset data in widgets.

        This method is called by the main GUI.
        """
        for widget in self._plot_widgets:
            widget.reset()

    def registerPlotWidget(self, instance):
        self._plot_widgets[instance] = 1

    def unregisterPlotWidget(self, instance):
        del self._plot_widgets[instance]


class AbstractSatelliteWindow(QtGui.QMainWindow):
    """Base class for Satellite windows.

    A satellite window does not need to access the data.
    """
    title = ""

    def __init__(self, parent=None):
        """Initialization."""
        super().__init__(parent=parent)
        if parent is not None:
            parent.registerWindow(self)

        self._mediator = Mediator()

        try:
            if self.title:
                title = parent.title + " - " + self.title
            else:
                title = parent.title

            self.setWindowTitle(title)
        except AttributeError:
            # for unit test where parent is None
            self.setWindowTitle(self.title)

    def initUI(self):
        """Initialization of UI.

        This method should call 'initCtrlUI' and 'initPlotUI'.
        """
        pass

    def initConnections(self):
        """Initialization of signal-slot connections."""
        pass

    def addToolBar(self):
        """Toolbar is not allowed."""
        raise NotImplementedError

    def closeEvent(self, QCloseEvent):
        parent = self.parent()
        if parent is not None:
            parent.unregisterWindow(self)
        super().closeEvent(QCloseEvent)