"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Mediator class.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject


class Mediator(QObject):
    """Mediator for GUI signal-slot connection."""

    bridge_endpoint_sgn = pyqtSignal(str)

    port_change_sgn = pyqtSignal(str)
    data_folder_change_sgn = pyqtSignal(str)

    start_file_server_sgn = pyqtSignal()
    stop_file_server_sgn = pyqtSignal()
    file_server_started_sgn = pyqtSignal()
    file_server_stopped_sgn = pyqtSignal()

    vip_pulse_id1_sgn = pyqtSignal(int)
    vip_pulse_id2_sgn = pyqtSignal(int)
    # tell the control widget to update VIP pulse IDs
    vip_pulse_ids_connected_sgn = pyqtSignal()
    photon_energy_change_sgn = pyqtSignal(float)
    sample_distance_change_sgn = pyqtSignal(float)

    roi_displayed_range_sgn = pyqtSignal(int)

    # index, device ID, property name, resolution
    correlation_param_change_sgn = pyqtSignal(int, str, str, float)
    correlation_fom_change_sgn = pyqtSignal(object)
    correlation_state_reset_sgn = pyqtSignal()

    reset_image_level_sgn = pyqtSignal()

    pulse_id_range_sgn = pyqtSignal(int, int)

    # (geometry file, quadrant positions)
    geometry_sgn = pyqtSignal(str, list)

    source_type_change_sgn = pyqtSignal(int)
    detector_source_change_sgn = pyqtSignal(str)
    xgm_source_change_sgn = pyqtSignal(str)
    mono_source_change_sgn = pyqtSignal(str)

    pp_pulse_ids_sgn = pyqtSignal(object, list, list)
    pp_ma_window_change_sgn = pyqtSignal(int)
    pp_abs_difference_sgn = pyqtSignal(bool)
    pp_analysis_type_sgn = pyqtSignal(object)
    pp_state_reset_sgn = pyqtSignal()

    proj1d_normalizer_change_sgn = pyqtSignal(object)
    proj1d_auc_x_range_change_sgn = pyqtSignal(float, float)
    proj1d_fom_integ_range_change_sgn = pyqtSignal(float, float)

    xas_state_set_sgn = pyqtSignal()
    xas_energy_bins_change_sgn = pyqtSignal(int)

    roi_region_change_sgn = pyqtSignal(int, bool, int, int, int, int)
    roi_fom_change_sgn = pyqtSignal(object)
    roi_hist_clear_sgn = pyqtSignal()

    __instance = None

    def __new__(cls, *args, **kwargs):
        """Create a singleton."""
        if cls.__instance is None:
            cls.__instance = super().__new__(cls, *args, **kwargs)
            cls.__instance._is_initialized = False
        return cls.__instance

    def __init__(self, *args, **kwargs):
        if self._is_initialized:
            return
        # this will reset all signal-slot connections
        super().__init__(*args, **kwargs)

        self._is_initialized = True

    def connect_scheduler(self, scheduler):
        # with the scheduler
        self.source_type_change_sgn.connect(scheduler.onSourceTypeChange)
        self.detector_source_change_sgn.connect(
            scheduler.onDetectorSourceChange)
        self.xgm_source_change_sgn.connect(scheduler.onXgmSourceChange)
        self.mono_source_change_sgn.connect(scheduler.onMonoSourceChange)
        self.pp_ma_window_change_sgn.connect(
            scheduler.onPumpProbeMAWindowChange)
        self.xas_state_set_sgn.connect(scheduler.onXasReset)
        self.xas_energy_bins_change_sgn.connect(scheduler.onXasEnergyBinsChange)
        self.roi_region_change_sgn.connect(scheduler.onRoiRegionChange)
        self.roi_fom_change_sgn.connect(scheduler.onRoiFomChange)
        self.roi_hist_clear_sgn.connect(scheduler.onRoiHistClear)

        self.pp_abs_difference_sgn.connect(scheduler.onPpDifferenceTypeChange)
        self.pp_analysis_type_sgn.connect(scheduler.onPpAnalysisTypeChange)
        self.pp_pulse_ids_sgn.connect(scheduler.onPpPulseStateChange)
        self.pp_state_reset_sgn.connect(scheduler.onPumpProbeReset)

        self.proj1d_normalizer_change_sgn.connect(
            scheduler.onProj1dNormalizerChange)
        self.proj1d_auc_x_range_change_sgn.connect(
            scheduler.onProj1dAucXRangeChange)
        self.proj1d_fom_integ_range_change_sgn.connect(
            scheduler.onProj1dFomIntegRangeChange)

        self.correlation_fom_change_sgn.connect(
            scheduler.onCorrelationFomChange)
        self.correlation_param_change_sgn.connect(
            scheduler.onCorrelationParamChange)
        self.correlation_state_reset_sgn.connect(
            scheduler.onCorrelationReset)

        self.pulse_id_range_sgn.connect(scheduler.onPulseIdRangeChange)
        self.photon_energy_change_sgn.connect(scheduler.onPhotonEnergyChange)
        self.sample_distance_change_sgn.connect(
            scheduler.onSampleDistanceChange)

        self.geometry_sgn.connect(scheduler.onGeometryChange)

    def connect_bridge(self, bridge):
        self.bridge_endpoint_sgn.connect(bridge.onEndpointChange)
        self.source_type_change_sgn.connect(bridge.onSourceTypeChange)
