import unittest
from unittest.mock import patch
import math
import os
import tempfile
import time

import numpy as np

from PyQt5.QtTest import QTest, QSignalSpy
from PyQt5.QtCore import Qt, QPoint

from karaboFAI.algorithms import mask_image
from karaboFAI.config import AnalysisType, config, _Config, ConfigWrapper, Normalizer
from karaboFAI.gui import mkQApp
from karaboFAI.gui.image_tool import ImageToolWindow
from karaboFAI.gui.image_tool.simple_image_data import _SimpleImageData
from karaboFAI.logger import logger
from karaboFAI.pipeline.data_model import ImageData, ProcessedData
from karaboFAI.pipeline.exceptions import ImageProcessingError
from karaboFAI.processes import wait_until_redis_shutdown
from karaboFAI.services import FAI

app = mkQApp()

logger.setLevel('CRITICAL')


class TestSimpleImageData(unittest.TestCase):
    @patch.dict(config._data, {"PIXEL_SIZE": 1e-3})
    def testGeneral(self):
        with self.assertRaises(TypeError):
            _SimpleImageData([1, 2, 3])

        gt_data = np.random.randn(3, 3).astype(np.float32)
        img_data = _SimpleImageData.from_array(gt_data)

        img_data.background = 1
        np.testing.assert_array_almost_equal(gt_data - 1, img_data.masked)
        img_data.background = 0
        np.testing.assert_array_almost_equal(gt_data, img_data.masked)

        img_data.threshold_mask = (3, 6)
        np.testing.assert_array_almost_equal(
            mask_image(gt_data, threshold_mask=(3, 6)), img_data.masked)
        img_data.background = 3
        np.testing.assert_array_almost_equal(
            mask_image(gt_data-3, threshold_mask=(3, 6)), img_data.masked)

        self.assertEqual(1.0e-3, img_data.pixel_size)

    @patch.dict(config._data, {"PIXEL_SIZE": 1e-3})
    def testInstantiateFromArray(self):
        gt_data = np.ones((2, 2, 2))

        image_data = _SimpleImageData.from_array(gt_data)

        np.testing.assert_array_equal(np.ones((2, 2)), image_data.masked)
        self.assertEqual(1e-3, image_data.pixel_size)
        self.assertEqual(0, image_data.background)
        self.assertEqual(None, image_data.threshold_mask)


class TestImageTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # do not use the config file in the current computer
        _Config._filename = os.path.join(tempfile.mkdtemp(), "config.json")
        ConfigWrapper()  # ensure file
        config.load('LPD')
        config.set_topic("FXE")

        cls.fai = FAI().init()
        cls.gui = cls.fai._gui
        cls.train_worker = cls.fai.train_worker
        cls.pulse_worker = cls.fai.pulse_worker

        actions = cls.gui._tool_bar.actions()
        cls._action = actions[3]
        assert("Image tool" == cls._action.text())

    @classmethod
    def tearDownClass(cls):
        cls.fai.terminate()

        wait_until_redis_shutdown()

    def setUp(self):
        ImageToolWindow.reset()
        self._action.trigger()
        self.image_tool = self.gui._image_tool
        self.view = self.image_tool._corrected_view.imageView
        self.view.setImageData(None)
        self.view._image = None

    def _get_data(self):
        return {'detector': {
                    'assembled': np.ones((4, 10, 10), np.float32),
                    'pulse_slicer': slice(None, None)},
                'processed': ProcessedData(1001)}

    def testGeneral(self):
        self.assertTrue(self.image_tool._pulse_resolved)
        self.assertTrue(self.image_tool._image_ctrl_widget._pulse_resolved)

    def testUpdateImage(self):
        widget = self.image_tool._image_ctrl_widget

        # test default values
        self.assertFalse(widget.update_image_btn.isEnabled())
        self.assertTrue(widget.auto_update_cb.isChecked())
        self.assertTrue(self.image_tool._auto_update)

        # test enabled and disable "update image" button
        widget.auto_update_cb.setChecked(False)
        self.assertTrue(widget.update_image_btn.isEnabled())
        self.assertFalse(self.image_tool._auto_update)
        widget.auto_update_cb.setChecked(True)
        self.assertFalse(widget.update_image_btn.isEnabled())
        self.assertTrue(self.image_tool._auto_update)

    def testDefaultValues(self):
        # This must be the first test method in order to check that the
        # default values are set correctly
        proc = self.train_worker._roi_proc
        widget = self.image_tool._corrected_view

        proc.update()

        for i, ctrl in enumerate(widget._roi_ctrls, 1):
            roi_geometry = [int(ctrl._px_le.text()),
                            int(ctrl._py_le.text()),
                            int(ctrl._width_le.text()),
                            int(ctrl._height_le.text())]
            self.assertListEqual(roi_geometry, getattr(proc, f"_roi{i}").rect)

    def testRoiCtrlWidget(self):
        widget = self.image_tool._corrected_view
        roi_ctrls = widget._roi_ctrls
        proc = self.train_worker._roi_proc
        self.assertEqual(4, len(roi_ctrls))

        for ctrl in roi_ctrls:
            self.assertFalse(ctrl.activate_cb.isChecked())
            self.assertFalse(ctrl.lock_cb.isChecked())
            self.assertFalse(ctrl._width_le.isEnabled())
            self.assertFalse(ctrl._height_le.isEnabled())
            self.assertFalse(ctrl._px_le.isEnabled())
            self.assertFalse(ctrl._py_le.isEnabled())

        roi1_ctrl = roi_ctrls[0]
        roi1 = self.view._rois[0]
        self.assertIs(roi1_ctrl._roi, roi1)

        # activate ROI1 ctrl
        QTest.mouseClick(roi1_ctrl.activate_cb, Qt.LeftButton,
                         pos=QPoint(2, roi1_ctrl.activate_cb.height()/2))
        self.assertTrue(roi1_ctrl.activate_cb.isChecked())
        proc.update()
        self.assertTrue(proc._roi1._activated)

        # test default values
        self.assertTupleEqual((float(roi1_ctrl._width_le.text()),
                               float(roi1_ctrl._height_le.text())),
                              tuple(roi1.size()))
        self.assertTupleEqual((float(roi1_ctrl._px_le.text()),
                               float(roi1_ctrl._py_le.text())),
                              tuple(roi1.pos()))

        # use keyClicks to test that the QLineEdit is enabled
        roi1_ctrl._width_le.clear()
        QTest.keyClicks(roi1_ctrl._width_le, "10")
        QTest.keyPress(roi1_ctrl._width_le, Qt.Key_Enter)
        roi1_ctrl._height_le.clear()
        QTest.keyClicks(roi1_ctrl._height_le, "30")
        QTest.keyPress(roi1_ctrl._height_le, Qt.Key_Enter)
        self.assertTupleEqual((10, 30), tuple(roi1.size()))

        # ROI can be outside of the image
        roi1_ctrl._px_le.clear()
        QTest.keyClicks(roi1_ctrl._px_le, "-1")
        QTest.keyPress(roi1_ctrl._px_le, Qt.Key_Enter)
        roi1_ctrl._py_le.clear()
        QTest.keyClicks(roi1_ctrl._py_le, "-3")
        QTest.keyPress(roi1_ctrl._py_le, Qt.Key_Enter)
        self.assertTupleEqual((-1, -3), tuple(roi1.pos()))

        proc.update()
        self.assertListEqual([-1, -3, 10, 30], proc._roi1.rect)

        # lock ROI ctrl
        QTest.mouseClick(roi1_ctrl.lock_cb, Qt.LeftButton,
                         pos=QPoint(2, roi1_ctrl.lock_cb.height()/2))
        self.assertTrue(roi1_ctrl.activate_cb.isChecked())
        self.assertTrue(roi1_ctrl.lock_cb.isChecked())
        self.assertFalse(roi1_ctrl._width_le.isEnabled())
        self.assertFalse(roi1_ctrl._height_le.isEnabled())
        self.assertFalse(roi1_ctrl._px_le.isEnabled())
        self.assertFalse(roi1_ctrl._py_le.isEnabled())

        # deactivate ROI ctrl
        QTest.mouseClick(roi1_ctrl.activate_cb, Qt.LeftButton,
                         pos=QPoint(2, roi1_ctrl.activate_cb.height()/2))
        self.assertFalse(roi1_ctrl.activate_cb.isChecked())
        self.assertTrue(roi1_ctrl.lock_cb.isChecked())
        self.assertFalse(roi1_ctrl._width_le.isEnabled())
        self.assertFalse(roi1_ctrl._height_le.isEnabled())
        self.assertFalse(roi1_ctrl._px_le.isEnabled())
        self.assertFalse(roi1_ctrl._py_le.isEnabled())

    def testMovingAverageQLineEdit(self):
        # TODO: remove it in the future
        widget = self.image_tool._image_ctrl_widget
        # moving average is disabled
        self.assertFalse(widget.moving_avg_le.isEnabled())

    @patch("karaboFAI.gui.plot_widgets.image_views.ImageAnalysis."
           "onThresholdMaskChange")
    @patch("karaboFAI.gui.mediator.Mediator.onImageThresholdMaskChange")
    def testThresholdMask(self, on_mask_mediator, on_mask):
        widget = self.image_tool._image_ctrl_widget

        widget.threshold_mask_le.clear()
        QTest.keyClicks(widget.threshold_mask_le, "1, 10")
        QTest.keyPress(widget.threshold_mask_le, Qt.Key_Enter)
        on_mask.assert_called_once_with((1, 10))
        on_mask_mediator.assert_called_once_with((1, 10))

    @patch("karaboFAI.gui.plot_widgets.image_views.ImageAnalysis."
           "onBkgChange")
    @patch("karaboFAI.gui.mediator.Mediator.onImageBackgroundChange")
    def testBackground(self, on_bkg_mediator, on_bkg):
        widget = self.image_tool._image_ctrl_widget

        widget.bkg_le.clear()
        QTest.keyClicks(widget.bkg_le, "1.1")
        QTest.keyPress(widget.bkg_le, Qt.Key_Enter)
        on_bkg.assert_called_once_with(1.1)
        on_bkg_mediator.assert_called_once_with(1.1)

    def testAutoLevel(self):
        widget = self.image_tool._image_ctrl_widget

        spy = QSignalSpy(self.image_tool._mediator.reset_image_level_sgn)
        widget.auto_level_btn.clicked.emit()
        self.assertEqual(1, len(spy))

    def testSetAndRemoveReference(self):
        widget = self.image_tool._image_ctrl_widget
        proc = self.pulse_worker._image_proc

        data = self._get_data()

        # test setting reference (no image)
        widget.set_ref_btn.clicked.emit()
        proc.process(data)
        self.assertIsNone(proc._reference)

        # test setting reference
        self.view._image = 2 * np.ones((10, 10), np.float32)
        widget.set_ref_btn.clicked.emit()
        proc.process(data)
        # This test fails randomly if 'testDrawMask', which is executed before
        # it, is not there.
        np.testing.assert_array_equal(self.view._image, proc._reference)

        # test removing reference
        widget.remove_ref_btn.clicked.emit()
        proc.process(data)
        self.assertIsNone(proc._reference)

        # test setting reference but the reference shape is different
        # from the image shape
        with self.assertRaises(ImageProcessingError):
            self.view._image = np.ones((2, 2), np.float32)
            widget.set_ref_btn.clicked.emit()
            proc.process(data)

    def testDrawMask(self):
        # TODO: test by really drawing something on ImageTool
        from karaboFAI.ipc import ImageMaskPub

        pub = ImageMaskPub()
        proc = self.pulse_worker._image_proc
        data = self._get_data()

        # trigger the lazily evaluated subscriber
        proc.process(data)
        self.assertIsNone(proc._image_mask)

        mask_gt = np.zeros(data['detector']['assembled'].shape[-2:], dtype=np.bool)

        pub.add((0, 0, 2, 3))
        mask_gt[0:3, 0:2] = True

        # test adding mask
        n_attempts = 0
        # FIXME: repeat to prevent random failure
        while n_attempts < 10:
            n_attempts += 1

            proc.process(data)
            # np.testing.assert_array_equal(mask_gt, proc._image_mask)
            if (mask_gt == proc._image_mask).all():
                break
            time.sleep(0.001)

        # add one more mask region
        pub.add((1, 1, 2, 3))
        proc.process(data)
        mask_gt[1:4, 1:3] = True
        np.testing.assert_array_equal(mask_gt, proc._image_mask)

        # test erasing mask
        pub.erase((2, 2, 3, 3))
        proc.process(data)
        mask_gt[2:5, 2:5] = False
        np.testing.assert_array_equal(mask_gt, proc._image_mask)

        # test trashing mask
        action = self.image_tool._tool_bar.actions()[2]
        action.trigger()
        proc.process(data)
        self.assertIsNone(proc._image_mask)

        # test set mask
        pub.set(mask_gt)
        proc.process(data)
        np.testing.assert_array_equal(mask_gt, proc._image_mask)

        # test set a mask which has a different shape from the image
        mask_gt = np.zeros((2, 2), dtype=np.bool)
        pub.set(mask_gt)
        with self.assertRaises(ImageProcessingError):
            proc.process(data)

    def testDarkRun(self):
        image_proc = self.pulse_worker._image_proc

        image_proc.update()
        self.assertFalse(image_proc._recording)

        # test "Recording dark" action
        self.assertFalse(self.image_tool._record_at.isEnabled())
        self.image_tool._views_tab.setCurrentWidget(self.image_tool._dark_view)
        self.assertTrue(self.image_tool._record_at.isEnabled())
        self.image_tool._record_at.trigger()
        image_proc.update()
        self.assertTrue(image_proc._recording)
        self.image_tool._views_tab.setCurrentWidget(self.image_tool._corrected_view)
        # disable "record AT" and stop recording when tab changes
        self.assertFalse(self.image_tool._record_at.isEnabled())
        self.assertFalse(self.image_tool._record_at.isChecked())
        image_proc.update()
        self.assertFalse(image_proc._recording)

        # test "Remove dark" action
        data = np.ones((10, 10), dtype=np.float32)
        image_proc._dark_run = data
        image_proc._dark_mean = data
        self.image_tool._remove_at.trigger()
        image_proc.update()
        self.assertIsNone(image_proc._dark_run)
        self.assertIsNone(image_proc._dark_mean)

        # test "subtract dark" checkbox
        self.assertTrue(image_proc._dark_subtraction)
        self.image_tool._image_ctrl_widget.darksubtraction_cb.setChecked(False)
        image_proc.update()
        self.assertFalse(image_proc._dark_subtraction)

    def testBulletinView(self):
        processed = ProcessedData(1357)

        processed.image = ImageData.from_array(np.ones((10, 4, 4), np.float32))
        processed.image.dark_count = 99
        processed.image.n_dark_pulses = 10
        processed.pidx.mask([1, 3, 5, 6])
        self.gui._queue.append(processed)
        self.image_tool.updateWidgetsF()

        view = self.image_tool._bulletin_view
        self.assertEqual(1357, int(view._latest_tid.intValue()))
        self.assertEqual(10, int(view._n_total_pulses.intValue()))
        self.assertEqual(6, int(view._n_kept_pulses.intValue()))
        self.assertEqual(99, int(view._dark_train_counter.intValue()))
        self.assertEqual(10, int(view._n_dark_pulses.intValue()))

    def testAzimuthalInteg1dCtrlWidget(self):
        from karaboFAI.pipeline.processors.azimuthal_integration import energy2wavelength

        widget = self.image_tool._azimuthal_integ_1d_view._ctrl_widget
        all_normalizers = {value: key for key, value in
                           widget._available_normalizers.items()}
        train_worker = self.train_worker
        proc = train_worker._ai_proc

        proc.update()

        self.assertAlmostEqual(config['SAMPLE_DISTANCE'], proc._sample_dist)
        self.assertAlmostEqual(energy2wavelength(config['PHOTON_ENERGY']), proc._wavelength)
        self.assertEqual(AnalysisType.UNDEFINED, proc.analysis_type)
        default_integ_method = 'BBox'
        self.assertEqual(default_integ_method, proc._integ_method)
        default_normalizer = Normalizer.UNDEFINED
        self.assertEqual(default_normalizer, proc._normalizer)
        self.assertEqual(config["AZIMUTHAL_INTEG_POINTS"], proc._integ_points)
        default_integ_range = tuple(config["AZIMUTHAL_INTEG_RANGE"])
        self.assertTupleEqual(tuple(config["AZIMUTHAL_INTEG_RANGE"]), proc._integ_range)
        self.assertTupleEqual(default_integ_range, proc._auc_range)
        self.assertTupleEqual(default_integ_range, proc._fom_integ_range)
        default_pixel_size = config["PIXEL_SIZE"]
        self.assertEqual(default_pixel_size, proc._pixel1)
        self.assertEqual(default_pixel_size, proc._pixel2)
        self.assertEqual(config["CENTER_Y"] * default_pixel_size, proc._poni1)
        self.assertEqual(config["CENTER_X"] * default_pixel_size, proc._poni2)

        widget._photon_energy_le.setText("12.4")
        widget._sample_dist_le.setText("0.3")
        widget._integ_method_cb.setCurrentText('nosplit_csr')
        widget._normalizers_cb.setCurrentText(all_normalizers[Normalizer.ROI3_ADD_ROI4])
        widget._integ_pts_le.setText(str(1024))
        widget._integ_range_le.setText("0.1, 0.2")
        widget._auc_range_le.setText("0.2, 0.3")
        widget._fom_integ_range_le.setText("0.3, 0.4")
        widget._px_le.setText("0.000001")
        widget._py_le.setText("0.000002")
        widget._cx_le.setText("-1000")
        widget._cy_le.setText("1000")
        proc.update()
        self.assertAlmostEqual(1e-10, proc._wavelength)
        self.assertAlmostEqual(0.3, proc._sample_dist)
        self.assertEqual('nosplit_csr', proc._integ_method)
        self.assertEqual(Normalizer.ROI3_ADD_ROI4, proc._normalizer)
        self.assertEqual(1024, proc._integ_points)
        self.assertTupleEqual((0.1, 0.2), proc._integ_range)
        self.assertTupleEqual((0.2, 0.3), proc._auc_range)
        self.assertTupleEqual((0.3, 0.4), proc._fom_integ_range)
        self.assertEqual(0.000001, proc._pixel2)
        self.assertEqual(0.000002, proc._pixel1)
        self.assertEqual(-1000 * 0.000001, proc._poni2)
        self.assertEqual(1000 * 0.000002, proc._poni1)

    def testProjection1DCtrlWidget(self):
        widget = self.image_tool._corrected_view._proj1d_ctrl_widget
        all_normalizers = {value: key for key, value in
                           widget._available_normalizers.items()}

        proc = self.train_worker._roi_proc
        proc.update()

        # test default reconfigurable values
        self.assertEqual('x', proc._direction)
        self.assertEqual(Normalizer.UNDEFINED, proc._normalizer)
        self.assertEqual((0, math.inf), proc._fom_integ_range)
        self.assertEqual((0, math.inf), proc._auc_range)

        # test setting new values
        widget._direct_cb.setCurrentText('y')
        widget._normalizers_cb.setCurrentText(all_normalizers[Normalizer.ROI3_SUB_ROI4])
        widget._fom_integ_range_le.setText("10, 20")
        widget._auc_range_le.setText("30, 40")
        proc.update()
        self.assertEqual('y', proc._direction)
        self.assertEqual(Normalizer.ROI3_SUB_ROI4, proc._normalizer)
        self.assertEqual((10, 20), proc._fom_integ_range)
        self.assertEqual((30, 40), proc._auc_range)

    def testGeometryCtrlWidget(self):
        from karabo_data.geometry2 import LPD_1MGeometry

        cw = self.image_tool._views_tab
        view = self.image_tool._geometry_view
        self.assertTrue(cw.isTabEnabled(cw.indexOf(view)))
        widget = view._ctrl_widget

        pulse_worker = self.pulse_worker

        widget._geom_file_le.setText(config["GEOMETRY_FILE"])
        self.assertTrue(widget.updateMetaData())
        pulse_worker._assembler.update()
        self.assertIsInstance(pulse_worker._assembler._geom, LPD_1MGeometry)

        widget._with_geometry_cb.setChecked(False)
        self.assertTrue(widget.updateMetaData())
        pulse_worker._assembler.update()
        self.assertIsNone(pulse_worker._assembler._geom)


class TestImageToolTs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # do not use the config file in the current computer
        _Config._filename = os.path.join(tempfile.mkdtemp(), "config.json")
        ConfigWrapper()  # ensure file
        config.load('JungFrau')
        config.set_topic("FXE")

        cls.fai = FAI().init()
        cls.gui = cls.fai._gui
        cls.train_worker = cls.fai.train_worker

        actions = cls.gui._tool_bar.actions()
        cls._action = actions[3]
        assert("Image tool" == cls._action.text())

    @classmethod
    def tearDownClass(cls):
        cls.fai.terminate()

        wait_until_redis_shutdown()

    def setUp(self):
        ImageToolWindow.reset()
        self._action.trigger()
        self.image_tool = self.gui._image_tool

    def testGeneral(self):
        self.assertFalse(self.image_tool._pulse_resolved)
        self.assertFalse(self.image_tool._image_ctrl_widget._pulse_resolved)

    def testMovingAverageQLineEdit(self):
        # TODO: remove it in the future
        widget = self.image_tool._image_ctrl_widget
        # moving average is disabled
        self.assertFalse(widget.moving_avg_le.isEnabled())

    def testGeometryCtrlWidget(self):
        cw = self.image_tool._views_tab
        view = self.image_tool._geometry_view
        self.assertFalse(cw.isTabEnabled(cw.indexOf(view)))
