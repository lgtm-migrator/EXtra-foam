"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Pipeline scheduler.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
from queue import Empty, Full

from scipy import constants

from PyQt5 import QtCore

from .image_assembler import ImageAssemblerFactory
from .data_aggregator import DataAggregator
from .data_model import ProcessedData
from .worker import Worker
from .processors import (
    AzimuthalIntegrationProcessor, _BaseProcessor, CorrelationProcessor,
    PumpProbeProcessorFactory, RoiProcessor, XasProcessor
)
from .exceptions import AggregatingError, AssemblingError, ProcessingError
from ..config import config, PumpProbeType
from ..helpers import profiler


class Scheduler(Worker):
    """Pipeline scheduler."""
    __instance = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls, *args, **kwargs)
        return cls.__instance

    def __init__(self):
        """Initialization."""
        super().__init__()

        self._tasks = []

        self._image_assembler = ImageAssemblerFactory.create(config['DETECTOR'])
        self._data_aggregator = DataAggregator()

        self._roi_proc = RoiProcessor()

        self._ai_proc = AzimuthalIntegrationProcessor()

        self._pp_proc = PumpProbeProcessorFactory.create(
            PumpProbeType.AZIMUTHAL_INTEGRATION)

        self._correlation_proc = CorrelationProcessor()

        self._xas_proc = XasProcessor()

    def __setattr__(self, key, value):
        if isinstance(value, _BaseProcessor):
            self._tasks.append(value)
        super().__setattr__(key, value)

    @QtCore.pyqtSlot(str)
    def onDetectorSourceChange(self, src):
        self._image_assembler.source_name = src

    @QtCore.pyqtSlot(int)
    def onSourceTypeChange(self, value):
        self._image_assembler.source_type = value

    @QtCore.pyqtSlot(str)
    def onXgmSourceChange(self, name):
        self._data_aggregator.xgm_src = name

    @QtCore.pyqtSlot(str)
    def onMonoSourceChange(self, name):
        self._data_aggregator.mono_src = name

    @QtCore.pyqtSlot(str, list)
    def onGeometryChange(self, filename, quad_positions):
        success, info = self._image_assembler.load_geometry(
            filename, quad_positions)
        if not success:
            self.log(info)

    @QtCore.pyqtSlot(int, int)
    def onPulseIdRangeChange(self, lb, ub):
        self._image_assembler.pulse_id_range = (lb, ub)

    @QtCore.pyqtSlot(object, list, list)
    def onPpPulseStateChange(self, mode, on_pulse_ids, off_pulse_ids):
        if mode != self._pp_proc.mode:
            self._pp_proc.mode = mode
            self._pp_proc.reset()
            ProcessedData.clear_pp_hist()

        self._pp_proc.on_pulse_ids = on_pulse_ids
        self._pp_proc.off_pulse_ids = off_pulse_ids

    @QtCore.pyqtSlot(object)
    def onPpAnalysisTypeChange(self, value):
        self._pp_proc.analysis_type = value

    @QtCore.pyqtSlot(int)
    def onPpDifferenceTypeChange(self, state):
        self._pp_proc.abs_difference = state == QtCore.Qt.Checked

    @QtCore.pyqtSlot(float, float)
    def onAucXRangeChange(self, lb, ub):
        self._ai_proc.auc_x_range = (lb, ub)

    @QtCore.pyqtSlot(object)
    def onAiNormalizeChange(self, normalizer):
        self._ai_proc.normalizer = normalizer

    @QtCore.pyqtSlot(float)
    def onSampleDistanceChange(self, value):
        self._ai_proc.sample_distance = value

    @QtCore.pyqtSlot(int, int)
    def onIntegrationCenterChange(self, cx, cy):
        self._ai_proc.integration_center = (cx, cy)

    @QtCore.pyqtSlot(str)
    def onIntegrationMethodChange(self, value):
        self._ai_proc.integration_method = value

    @QtCore.pyqtSlot(float, float)
    def onIntegrationRangeChange(self, lb, ub):
        self._ai_proc.integration_range = (lb, ub)

    @QtCore.pyqtSlot(int)
    def onIntegrationPointsChange(self, value):
        self._ai_proc.integration_points = value

    @QtCore.pyqtSlot(float)
    def onPhotonEnergyChange(self, photon_energy):
        """Compute photon wavelength (m) from photon energy (keV)."""
        # Plank-einstein relation (E=hv)
        HC_E = 1e-3 * constants.c * constants.h / constants.e
        self._ai_proc.wavelength = HC_E / photon_energy

    @QtCore.pyqtSlot(float, float)
    def onFomIntegrationRangeChange(self, lb, ub):
        self._ai_proc.fom_itgt_range = (lb, ub)
        self._pp_proc.fom_itgt_range = (lb, ub)
        self._correlation_proc.fom_itgt_range = (lb, ub)

    @QtCore.pyqtSlot()
    def onPumpProbeReset(self):
        ProcessedData.clear_pp_hist()
        self._pp_proc.reset()

    @QtCore.pyqtSlot(int)
    def onEnableAiStateChange(self, state):
        enabled = state == QtCore.Qt.Checked
        self._ai_proc.enabled = enabled

    @QtCore.pyqtSlot()
    def onCorrelationReset(self):
        ProcessedData.clear_correlation_hist()

    @QtCore.pyqtSlot(int, str, str, float)
    def onCorrelationParamChange(self, idx, device_id, ppt, resolution):
        ProcessedData.add_correlator(idx, device_id, ppt, resolution)

    @QtCore.pyqtSlot(object)
    def onCorrelationFomChange(self, fom):
        if self._correlation_proc.fom_name != fom:
            self._correlation_proc.fom_name = fom
            ProcessedData.clear_correlation_hist()

    @QtCore.pyqtSlot(int)
    def onPumpProbeMAWindowChange(self, n):
        self._pp_proc.ma_window = n

    @QtCore.pyqtSlot(int)
    def onXasEnergyBinsChange(self, n):
        self._xas_proc.n_bins = n

    @QtCore.pyqtSlot()
    def onXasReset(self):
        self._xas_proc.reset()

    @QtCore.pyqtSlot(int, bool, int, int, int, int)
    def onRoiRegionChange(self, rank, activated, w, h, px, py):
        if activated:
            self._roi_proc.set(rank, (w, h, px, py))
        else:
            self._roi_proc.set(rank, None)

    @QtCore.pyqtSlot(object)
    def onRoiFomChange(self, value):
        self._roi_proc.roi_fom = value
        ProcessedData.clear_roi_hist()

    def clear_roi_hist(self):
        ProcessedData.clear_roi_hist()

    def run(self):
        """Run the data processor."""
        self._running = True
        self.log("Data processor started!")
        while self._running:
            try:
                data = self._input.get(timeout=config['TIMEOUT'])
            except Empty:
                continue

            processed_data = self._process(data)
            if processed_data is None:
                continue

            while self._running:
                try:
                    self._output.put(processed_data, timeout=config['TIMEOUT'])
                    break
                except Full:
                    continue

        self.log("Data processor stopped!")

    @profiler("Process Data (total)")
    def _process(self, data):
        """Process data received from the bridge."""
        raw, meta = data

        # get the train ID of the first metadata
        # Note: this is better than meta[src_name] because:
        #       1. For streaming AGIPD/LPD data from files, 'src_name' does
        #          not work;
        #       2. Prepare for the scenario where a 2D detector is not
        #          mandatory.
        tid = next(iter(meta.values()))["timestamp.tid"]

        try:
            assembled = self._image_assembler.assemble(raw)
        except AssemblingError as e:
            self.log(f"Train ID: {tid}: " + repr(e))
            return None
        except Exception as e:
            self.log(f"Unexpected Exception: Train ID: {tid}: " + repr(e))
            raise

        try:
            processed = ProcessedData(tid, assembled)
        except Exception as e:
            self.log(f"Unexpected Exception: Train ID: {tid}: " + repr(e))
            raise

        try:
            self._data_aggregator.aggregate(processed, raw)
        except AggregatingError as e:
            self.log(f"Train ID: {tid}: " + repr(e))
        except Exception as e:
            self.log(f"Unexpected Exception: Train ID: {tid}: " + repr(e))
            raise

        for task in self._tasks:
            try:
                task.run_once(processed, raw)
            except ProcessingError as e:
                self.log(f"Train ID: {tid}: " + repr(e))
            except Exception as e:
                self.log(f"Unexpected Exception: Train ID: {tid}: " + repr(e))
                raise

        return processed
