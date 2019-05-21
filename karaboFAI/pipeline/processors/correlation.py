"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

CorrelationProcessor.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
import numpy as np

from .base_processor import LeafProcessor, CompositeProcessor, SharedProperty
from ..exceptions import ProcessingError
from ...algorithms import slice_curve
from ...config import config, CorrelationFom
from ...metadata import Metadata as mt
from ...helpers import profiler


class CorrelationProcessor(CompositeProcessor):
    """Add correlation information into processed data.

    Attributes:
        fom_type (CorrelationFom): type of the figure-of-merit
        fom_integ_range (tuple): integration range for calculating FOM from
            the normalized azimuthal integration.
    """
    fom_integ_range = SharedProperty()
    fom_type = SharedProperty()
    device_ids = SharedProperty()
    properties = SharedProperty()

    def __init__(self):
        super().__init__()

        n_params = len(config["CORRELATION_COLORS"])
        self.device_ids = [""] * n_params
        self.properties = [""] * n_params

        self.add(CorrelationFomProcessor())

    def update(self):
        cfg = self._meta.get_all(mt.CORRELATION_PROC)
        self.fom_type = CorrelationFom(int(cfg['fom_type']))

        self.fom_integ_range = self.str2tuple(
            self._meta.get(mt.AZIMUTHAL_INTEG_PROC, 'integ_range'))

        for i in range(len(self.device_ids)):
            self.device_ids[i] = cfg[f'device_id{i+1}']
            self.properties[i] = cfg[f'property{i+1}']


class CorrelationFomProcessor(LeafProcessor):
    @profiler("Correlation processor")
    def process(self, processed, raw=None):
        """Override."""
        if self.fom_type is None or self.fom_type == CorrelationFom.UNDEFINED:
            return

        if self.fom_type == CorrelationFom.PUMP_PROBE_FOM:
            fom = processed.pp.fom
            if fom is None:
                raise ProcessingError(
                    "Pump-probe result is not available!")

        elif self.fom_type == CorrelationFom.ROI1:
            fom = processed.roi.roi1_fom
            if fom is None:
                raise ProcessingError("ROI1 result is not available!")

        elif self.fom_type == CorrelationFom.ROI2:
            fom = processed.roi.roi2_fom
            if fom is None:
                raise ProcessingError("ROI2 result is not available!")

        elif self.fom_type == CorrelationFom.ROI_SUM:
            fom1 = processed.roi.roi1_fom
            if fom1 is None:
                raise ProcessingError("ROI1 result is not available!")
            fom2 = processed.roi.roi2_fom
            if fom2 is None:
                raise ProcessingError("ROI2 result is not available!")

            fom = fom1 + fom2

        elif self.fom_type == CorrelationFom.ROI_SUB:
            fom1 = processed.roi.roi1_fom
            if fom1 is None:
                raise ProcessingError("ROI1 result is not available!")
            fom2 = processed.roi.roi2_fom
            if fom2 is None:
                raise ProcessingError("ROI2 result is not available!")

            fom = fom1 - fom2

        elif self.fom_type == CorrelationFom.AZIMUTHAL_INTEG_MEAN:
            momentum = processed.ai.momentum
            if momentum is None:
                raise ProcessingError(
                    "Azimuthal integration result is not available!")
            intensity = processed.ai.intensity_mean

            # calculate figure-of-merit
            fom = slice_curve(intensity, momentum, *self.fom_integ_range)[0]
            fom = np.sum(np.abs(fom))

        else:
            name = str(self.fom_type).split(".")[-1]
            raise ProcessingError(f"Unknown FOM name: {name}!")

        processed.correlation.fom = fom

        # get the correlator values

        for i in range(1, len(self.device_ids)+1):
            device_id = self.device_ids[i-1]
            if not device_id:
                continue

            ppt = self.properties[i-1]
            if not ppt:
                continue

            if device_id == "Any":
                # orig_data cannot be empty here
                setattr(processed.correlation,
                        f'correlator{i}',
                        processed.tid)
            else:
                try:
                    device_data = raw[device_id]
                except KeyError:
                    raise ProcessingError(
                        f"Device '{device_id}' is not in the data!")

                try:
                    if ppt not in device_data:
                        # from file
                        ppt += '.value'

                    setattr(processed.correlation,
                            f'correlator{i}',
                            device_data[ppt])

                except KeyError:
                    raise ProcessingError(
                        f"'{device_id}'' does not have property '{ppt}'")
