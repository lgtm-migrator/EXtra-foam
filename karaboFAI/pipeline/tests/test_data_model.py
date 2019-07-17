import unittest
from unittest.mock import patch

import numpy as np

from karaboFAI.pipeline.data_model import (
    AbstractData, AccumulatedPairData, DataManagerMixin,
    ImageData, ProcessedData, PumpProbeData, RawImageData, RoiData,
    PairData
)
from karaboFAI.config import config


class TestPairData(unittest.TestCase):
    def test_general(self):
        class Dummy(AbstractData):
            values = PairData()

        dm = Dummy()

        dm.values = (1, 10)
        dm.values = (2, 20)
        tids, values, _ = dm.values
        np.testing.assert_array_equal([1, 2], tids)
        np.testing.assert_array_equal([10, 20], values)

        dm.values = (3, 30)
        tids, values, _ = dm.values
        np.testing.assert_array_equal([1, 2, 3], tids)
        np.testing.assert_array_equal([10, 20, 30], values)

        del dm.values
        tids, values, _ = dm.values
        np.testing.assert_array_equal([2, 3], tids)
        np.testing.assert_array_equal([20, 30], values)

        Dummy.clear()
        tids, values, _ = dm.values
        np.testing.assert_array_equal([], tids)
        np.testing.assert_array_equal([], values)


class TestRawImageData(unittest.TestCase):
    # This also tests MovingAverageArray
    data = RawImageData()

    def testTrainResolved(self):
        arr = np.ones((3, 3), dtype=np.float32)
        self.data = arr.copy()

        self.assertEqual(1, self.__class__.data.n_images)

        self.__class__.data.window = 5
        self.assertEqual(5, self.__class__.data.window)
        self.assertEqual(1, self.__class__.data.count)
        self.data = 3 * arr
        self.assertEqual(5, self.__class__.data.window)
        self.assertEqual(2, self.__class__.data.count)
        np.testing.assert_array_equal(2 * arr, self.data)

        # set a ma window which is smaller than the current window
        self.__class__.data.window = 3
        self.assertEqual(3, self.__class__.data.window)
        self.assertEqual(2, self.__class__.data.count)
        np.testing.assert_array_equal(2 * arr, self.data)

        # set an image with a different shape
        new_arr = 2*np.ones((3, 1), dtype=np.float32)
        self.data = new_arr
        self.assertEqual(3, self.__class__.data.window)
        self.assertEqual(1, self.__class__.data.count)
        np.testing.assert_array_equal(new_arr, self.data)

    def testPulseResolved(self):
        arr = np.ones((3, 4, 4), dtype=np.float32)

        self.assertEqual(0, self.__class__.data.n_images)

        self.data = arr.copy()
        self.assertEqual(3, self.__class__.data.n_images)

        self.__class__.data.window = 10
        self.assertEqual(10, self.__class__.data.window)
        self.assertEqual(1, self.__class__.data.count)
        self.data = 5 * arr
        self.assertEqual(10, self.__class__.data.window)
        self.assertEqual(2, self.__class__.data.count)
        np.testing.assert_array_equal(3 * arr, self.data)

        # set a ma window which is smaller than the current window
        self.__class__.data.window = 2
        self.assertEqual(2, self.__class__.data.window)
        self.assertEqual(2, self.__class__.data.count)
        np.testing.assert_array_equal(3 * arr, self.data)

        # set a data with a different number of images
        new_arr = 5*np.ones((5, 4, 4))
        self.data = new_arr
        self.assertEqual(2, self.__class__.data.window)
        self.assertEqual(1, self.__class__.data.count)
        np.testing.assert_array_equal(new_arr, self.data)


class TestCorrelationData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._manager = DataManagerMixin()

    def setUp(self):
        self._manager.remove_correlations()

    def testPairData(self):
        data = ProcessedData(1, np.zeros((2, 2)))

        with self.assertRaises(ValueError):
            self._manager.add_correlation(0, "device1", "property1")

        self._manager.add_correlation(1, "device1", "property1")
        data.correlation.correlation1 = (1, 0.5)
        data.correlation.correlation1 = (2, 0.6)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_almost_equal([1, 2], corr_hist)
        np.testing.assert_array_almost_equal([0.5, 0.6], fom_hist)
        self.assertEqual("device1", info["device_id"])
        self.assertEqual("property1", info["property"])

        self._manager.add_correlation(2, "device2", "property2")
        data.correlation.correlation2 = (3, 200)
        data.correlation.correlation2 = (4, 220)
        corr_hist, fom_hist, info = data.correlation.correlation2
        np.testing.assert_array_almost_equal([3, 4], corr_hist)
        np.testing.assert_array_almost_equal([200, 220], fom_hist)
        self.assertEqual("device2", info["device_id"])
        self.assertEqual("property2", info["property"])
        # check that correlation1 remains unchanged
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_almost_equal([1, 2], corr_hist)
        np.testing.assert_array_almost_equal([0.5, 0.6], fom_hist)
        self.assertEqual("device1", info["device_id"])
        self.assertEqual("property1", info["property"])

        # test clear history
        data.correlation.reset = True
        data.correlation.update_hist(2)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_almost_equal([], corr_hist)
        np.testing.assert_array_almost_equal([], fom_hist)
        self.assertEqual("device1", info["device_id"])
        self.assertEqual("property1", info["property"])
        corr_hist, fom_hist, info = data.correlation.correlation2
        np.testing.assert_array_almost_equal([], corr_hist)
        np.testing.assert_array_almost_equal([], fom_hist)
        self.assertEqual("device2", info["device_id"])
        self.assertEqual("property2", info["property"])

        # when device_id or property is empty, the corresponding 'param'
        # will be removed
        self._manager.add_correlation(1, "", "property2")
        with self.assertRaises(AttributeError):
            data.correlation.correlation1

        self._manager.add_correlation(2, "device2", "")
        with self.assertRaises(AttributeError):
            data.correlation.correlation2

        # test CorrelationData.remove_correlations()
        self._manager.add_correlation(1, "device1", "property1")
        self._manager.add_correlation(2, "device1", "property1")
        self.assertListEqual(['correlation1', 'correlation2'],
                             self._manager.get_correlations())
        self._manager.remove_correlations()
        self.assertListEqual([], self._manager.get_correlations())

        # test when resolution becomes non-zero
        self._manager.add_correlation(1, "device1", "property1", 0.2)
        self.assertIsInstance(data.correlation.__class__.__dict__['correlation1'],
                              AccumulatedPairData)

        # ----------------------------
        # test when max length reached
        # ----------------------------

        self._manager.add_correlation(1, "device1", "property1")
        # override the class attribute
        max_len = 1000
        data.correlation.__class__.__dict__['correlation1'].MAX_LENGTH = max_len
        overflow = 10
        for i in range(max_len + overflow):
            data.correlation.correlation1 = (i, i)
        corr, fom, _ = data.correlation.correlation1
        self.assertEqual(max_len, len(corr))
        self.assertEqual(max_len, len(fom))
        self.assertEqual(overflow, corr[0])
        self.assertEqual(overflow, fom[0])
        self.assertEqual(max_len + overflow - 1, corr[-1])
        self.assertEqual(max_len + overflow - 1, fom[-1])

    def testAccumulatedPairData(self):
        data = ProcessedData(1, np.zeros((2, 2)))
        self.assertEqual(2, AccumulatedPairData._min_count)

        self._manager.add_correlation(1, "device1", "property1", 0.1)
        data.correlation.correlation1 = (1, 0.3)
        data.correlation.correlation1 = (2, 0.4)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_equal([], corr_hist)
        np.testing.assert_array_equal([], fom_hist.count)
        np.testing.assert_array_equal([], fom_hist.avg)
        np.testing.assert_array_equal([], fom_hist.min)
        np.testing.assert_array_equal([], fom_hist.max)

        data.correlation.correlation1 = (2.02, 0.5)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_equal([2.01], corr_hist)
        np.testing.assert_array_equal([2], fom_hist.count)
        np.testing.assert_array_almost_equal([0.425], fom_hist.min)
        np.testing.assert_array_almost_equal([0.475], fom_hist.max)
        np.testing.assert_array_equal([0.45], fom_hist.avg)

        data.correlation.correlation1 = (2.11, 0.6)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_equal([3], fom_hist.count)
        np.testing.assert_array_almost_equal([0.4591751709536137], fom_hist.min)
        np.testing.assert_array_almost_equal([0.5408248290463863], fom_hist.max)
        np.testing.assert_array_equal([0.5], fom_hist.avg)

        # new point
        data.correlation.correlation1 = (2.31, 1)
        data.correlation.correlation1 = (2.41, 2)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_equal([3, 2], fom_hist.count)
        np.testing.assert_array_almost_equal([0.4591751709536137, 1.25], fom_hist.min)
        np.testing.assert_array_almost_equal([0.5408248290463863, 1.75], fom_hist.max)
        np.testing.assert_array_equal([0.5, 1.5], fom_hist.avg)

        # test when resolution changes
        self._manager.add_correlation(1, "device1", "property1", 0.2)
        corr_hist, fom_hist, info = data.correlation.correlation1
        np.testing.assert_array_equal([], corr_hist)
        np.testing.assert_array_equal([], fom_hist.count)
        np.testing.assert_array_equal([], fom_hist.min)
        np.testing.assert_array_equal([], fom_hist.max)
        np.testing.assert_array_equal([], fom_hist.avg)

        # test when resolution becomes 0
        self._manager.add_correlation(1, "device1", "property1")
        self.assertIsInstance(data.correlation.__class__.__dict__['correlation1'],
                              PairData)

        # ----------------------------
        # test when max length reached
        # ----------------------------

        self._manager.add_correlation(1, "device1", "property1", 1.0)
        # override the class attribute
        max_len = 1000
        data.correlation.__class__.__dict__['correlation1'].MAX_LENGTH = max_len
        overflow = 10
        for i in range(2*max_len + 2*overflow):
            # two adjacent data point will be grouped together since
            # resolution is 1.0
            data.correlation.correlation1 = (i, i)
        corr_hist, fom_hist, _ = data.correlation.correlation1
        self.assertEqual(max_len, len(corr_hist))
        self.assertEqual(max_len, len(fom_hist.avg))
        self.assertEqual(2*overflow + 0.5, corr_hist[0])
        self.assertEqual(2*overflow + 0.5, fom_hist.avg[0])
        self.assertEqual(2*(max_len + overflow - 1) + 0.5, corr_hist[-1])
        self.assertEqual(2*(max_len + overflow - 1) + 0.5, fom_hist.avg[-1])


class TestProcessedData(unittest.TestCase):
    def testGeneral(self):
        # ---------------------
        # pulse-resolved data
        # ---------------------

        data = ProcessedData(1234, np.zeros((1, 2, 2)))

        self.assertEqual(1234, data.tid)
        self.assertEqual(1, data.n_pulses)
        self.assertTrue(data.pulse_resolved)

        data = ProcessedData(1235, np.zeros((3, 2, 2)))

        self.assertEqual(3, data.n_pulses)
        self.assertTrue(data.pulse_resolved)

        # ---------------------
        # train-resolved data
        # ---------------------

        data = ProcessedData(1236, np.zeros((2, 2)))

        self.assertEqual(1236, data.tid)
        self.assertEqual(1, data.n_pulses)
        self.assertFalse(data.pulse_resolved)


class TestImageData(unittest.TestCase):

    def testInvalidInput(self):
        with self.assertRaises(TypeError):
            ImageData()

        with self.assertRaises(ValueError):
            ImageData(np.arange(2))

        with self.assertRaises(ValueError):
            ImageData(np.arange(16).reshape((2, 2, 2, 2)))

    @patch.dict(config._data, {'PIXEL_SIZE': 1e-3})
    def testInitWithDefaultParameters(self):

        # ---------------------
        # pulse-resolved data
        # ---------------------

        # test automatically convert dtype to np.float32
        self.assertEqual(ImageData(np.arange(4).reshape((2, 2))).mean.dtype,
                         np.float32)

        image_data = ImageData(np.ones((4, 2, 2)))
        self.assertEqual(1e-3, image_data.pixel_size)
        self.assertEqual(4, image_data.n_images)
        self.assertTupleEqual((2, 2), image_data.shape)
        self.assertTrue(image_data.pulse_resolved)
        np.testing.assert_array_equal(np.ones((4, 2, 2)), image_data.images)
        np.testing.assert_array_equal(np.ones((2, 2)), image_data.mean)
        np.testing.assert_array_equal(np.ones((2, 2)), image_data.masked_mean)
        self.assertEqual(0.0, image_data.background)
        self.assertEqual((-np.inf, np.inf), image_data.threshold_mask)
        self.assertEqual(1, image_data.ma_window)
        self.assertEqual(1, image_data.ma_count)

        # ---------------------
        # train-resolved data
        # ---------------------

        image_data = ImageData(np.array([[1, 0], [np.nan, 1]]))

        self.assertEqual(1, image_data.n_images)
        self.assertTupleEqual((2, 2), image_data.shape)
        self.assertFalse(image_data.pulse_resolved)
        np.testing.assert_array_equal(np.array([[1, 0], [np.nan, 1]]),
                                      image_data.mean)
        self.assertIs(image_data.mean, image_data.images)
        # nan should be converted to 0 after masking
        np.testing.assert_array_equal(np.array([[1, 0], [0, 1]]),
                                      image_data.masked_mean)
        self.assertIsNot(image_data.masked_mean, image_data.mean)

    @patch.dict(config._data, {'PIXEL_SIZE': 2e-3})
    def testInitWithSpecifiedParameters(self):

        # test raise
        with self.assertRaises(TypeError):
            ImageData(np.ones((2, 2, 2)), keep=1)

        # ---------------------
        # pulse-resolved data
        # ---------------------
        imgs = np.ones((3, 2, 2))
        imgs[:, 0, :] = 2
        image_data = ImageData(imgs,
                               threshold_mask=(0, 1),
                               ma_window=4,
                               ma_count=2,
                               background=-100,
                               keep=[0, 1])
        self.assertEqual(2e-3, image_data.pixel_size)
        self.assertEqual(3, image_data.n_images)
        # image_data.images become a list when 'keep' is given.
        np.testing.assert_array_equal(np.array([[2., 2.], [1., 1.]]),
                                      image_data.images[0])
        np.testing.assert_array_equal(np.array([[2., 2.], [1., 1.]]),
                                      image_data.images[1])
        self.assertIsNone(image_data.images[2])
        np.testing.assert_array_equal(np.array([[2., 2.], [1., 1.]]),
                                      image_data.mean)
        np.testing.assert_array_equal(np.array([[0., 0.], [1., 1.]]),
                                      image_data.masked_mean)
        self.assertEqual(-100, image_data.background)
        self.assertEqual((0, 1), image_data.threshold_mask)
        self.assertEqual(4, image_data.ma_window)
        self.assertEqual(2, image_data.ma_count)

        # ---------------------
        # train-resolved data
        # ---------------------
        img = np.ones((2, 2))
        img[0, 0] = 2
        image_data = ImageData(img, threshold_mask=(0, 1))

        self.assertEqual(1, image_data.n_images)
        self.assertTupleEqual((2, 2), image_data.shape)
        np.testing.assert_array_equal(np.array([[2., 1.], [1., 1.]]),
                                      image_data.mean)
        np.testing.assert_array_equal(np.array([[0., 1.], [1., 1.]]),
                                      image_data.masked_mean)


class TestPumpProbeData(unittest.TestCase):
    def testGeneral(self):
        data = PumpProbeData()

        self.assertEqual(1, data.ma_window)
        self.assertEqual(0, data.ma_count)

        window = 6

        data.ma_window = window
        self.assertEqual(window, data.ma_window)

        x_gt = np.ones(10)  # x should not change
        this_on = 15 * np.ones(10)
        this_off = 10 * np.ones(10)
        on_gt = np.copy(this_on)
        off_gt = np.copy(this_off)

        # test reset
        data.data = (x_gt, this_on, this_off)
        data.reset = True
        data.update_hist()
        self.assertEqual(1, data.ma_window)
        self.assertEqual(0, data.ma_count)

        # set data again
        data.ma_window = window
        data.data = (x_gt, this_on, this_off)
        # count < window size
        for i in range(data.ma_window - 1):
            data.data = (x_gt, this_on - 2 - i, this_off - 2 - i)
            x, on, off = data.data
            on_gt -= 1
            off_gt -= 1
            np.testing.assert_array_equal(x_gt, x)
            np.testing.assert_array_equal(on_gt, on)
            np.testing.assert_array_equal(off_gt, off)
        self.assertEqual(window, data.ma_count)

        # on = 10 * np.ones(1), off = 5 * np.ones(1)
        x, on, off = data.data

        this_on = 4 * np.ones(10)
        this_off = 2 * np.ones(10)
        data.data = (x_gt, this_on, this_off)
        self.assertEqual(window, data.ma_count)
        x, on, off = data.data
        np.testing.assert_array_equal(9 * np.ones(10), on)  # 10 + (4 - 10)/6
        np.testing.assert_array_equal(4.5 * np.ones(10), off)  # 5 + (2 - 5)/6


class TestRoiData(unittest.TestCase):
    def test_general(self):
        data = RoiData()

        n_rois = len(config["ROI_COLORS"])
        for i in range(1, n_rois+1):
            self.assertTrue(hasattr(RoiData, f"roi{i}_hist"))
            self.assertIsInstance(getattr(RoiData, f"roi{i}_hist"), PairData)
            self.assertTrue(hasattr(data, f"roi{i}"))

        with self.assertRaises(AttributeError):
            getattr(RoiData, f"roi{n_rois+1}_hist")

        with self.assertRaises(AttributeError):
            getattr(data, f"roi{n_rois+1}")
