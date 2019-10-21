"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Unittest for PulseFilterProcessor.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
from unittest.mock import MagicMock

import numpy as np

from karaboFAI.pipeline.processors import XgmPulseFilter, PostPulseFilter
from karaboFAI.pipeline.exceptions import ProcessingError
from karaboFAI.config import AnalysisType
from karaboFAI.pipeline.processors.tests import _BaseProcessorTest


class TestPulseFilters(_BaseProcessorTest):
    def testXgmPulseFilter(self):
        proc = XgmPulseFilter()

    def testPostPulseFilter(self):
        proc = PostPulseFilter()

        # Note: sequence of the test should be the opposite of the sequence
        #       of "if elif else" in the 'process' method

        # AZIMUTHAL_INTEG
        data, processed = self.simple_data(1001, (4, 2, 2))
        proc.analysis_type = AnalysisType.AZIMUTHAL_INTEG_PULSE
        with self.assertRaises(NotImplementedError):
            proc.process(data)

        # ROI2
        data, processed = self.simple_data(1001, (4, 2, 2))
        proc.analysis_type = AnalysisType.ROI1_PULSE
        with self.assertRaises(ProcessingError):
            proc.process(data)  # FOM is not available
        self.assertEqual([], processed.image.dropped_indices)
        processed.pulse.roi.roi1.fom = [1, 2, 3, 4]
        proc.process(data)
        self.assertEqual([], processed.image.dropped_indices)
        proc._fom_range = [0, 2.5]
        proc.process(data)
        self.assertEqual([2, 3], processed.image.dropped_indices)

        # ROI1
        data, processed = self.simple_data(1001, (4, 2, 2))
        proc.analysis_type = AnalysisType.ROI2_PULSE
        with self.assertRaises(ProcessingError):
            proc.process(data)  # FOM is not available
        self.assertEqual([], processed.image.dropped_indices)
        processed.pulse.roi.roi2.fom = [4, 5, 6, 7]
        proc._fom_range = [0, 2.5]
        proc.process(data)
        self.assertEqual([0, 1, 2, 3], processed.image.dropped_indices)

        # UNDEFINED
        data, processed = self.simple_data(1001, (4, 2, 2))
        proc.analysis_type = AnalysisType.UNDEFINED
        proc.process(data)
        self.assertEqual([], processed.image.dropped_indices)
