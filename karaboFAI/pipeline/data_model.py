"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Data models for analysis and visualization.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
import copy
from threading import Lock

import numpy as np

from ..algorithms import mask_image

from ..config import config

from karaboFAI.cpp import xt_nanmean_images, xt_moving_average


class PairData:
    """Store the history pair data.

    Each data point is pair of data: (x, y).

    For correlation plots: x can be a train ID or a motor position,
    and y is the figure of merit (FOM).
    """
    MAX_LENGTH = 3000  # scatter plot is expensive

    def __init__(self, **kwargs):
        # We need to have a 'x' for each sub-dataset due to the
        # concurrency of data processing.
        self._x = []
        self._y = []
        # for now it is used in CorrelationData to store device ID and
        # property information
        self._info = kwargs

        self._lock = Lock()

    def __get__(self, instance, instance_type):
        if instance is None:
            return self
        # Note: here we must ensure that the data is not copied
        with self._lock:
            x = np.array(self._x)
            y = np.array(self._y)
            info = copy.copy(self._info)
        return x, y, info

    def __set__(self, instance, pair):
        this_x, this_y = pair
        with self._lock:
            self._x.append(this_x)
            self._y.append(this_y)

        # This is a reasonable choice since we always wants to return a
        # reference in __get__!
        if len(self._x) > self.MAX_LENGTH:
            self.__delete__(instance)

    def __delete__(self, instance):
        with self._lock:
            del self._x[0]
            del self._y[0]

    def clear(self):
        with self._lock:
            self._x.clear()
            self._y.clear()
        # do not clear _info here!


class AccumulatedPairData(PairData):
    """Store the history accumulated pair data.

    Each data point is pair of data: (x, DataStat).

    The data is collected in a stop-and-collected way. A motor,
    for example, will stop in a location and collect data for a
    period of time. Then,  each data point in the accumulated
    pair data is the average of the data during this period.
    """
    class DataStat:
        """Statistic of data."""
        def __init__(self):
            self.count = None
            self.avg = None
            self.min = None
            self.max = None

    MAX_LENGTH = 600

    _min_count = 2
    _epsilon = 1e-9

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'resolution' not in kwargs:
            raise ValueError("'resolution' is required!")
        resolution = kwargs['resolution']
        if resolution <= 0:
            raise ValueError("'resolution must be positive!")
        self._resolution = resolution

        self._y_count = []
        self._y_avg = []
        self._y_min = []
        self._y_max = []
        self._y_std = []

    def __set__(self, instance, pair):
        this_x, this_y = pair
        with self._lock:
            if self._x:
                if abs(this_x - self._x[-1]) - self._resolution < self._epsilon:
                    self._y_count[-1] += 1
                    avg_prev = self._y_avg[-1]
                    self._y_avg[-1] += \
                        (this_y - self._y_avg[-1]) / self._y_count[-1]
                    self._y_std[-1] += \
                        (this_y - avg_prev)*(this_y - self._y_avg[-1])
                    # self._y_min and self._y_max does not store min and max
                    # Only Standard deviation will be plotted. Min Max functionality
                    # does not exist as of now.
                    # self._y_min stores y_avg - 0.5*std_dev
                    # self._y_max stores y_avg + 0.5*std_dev
                    self._y_min[-1] = self._y_avg[-1] - 0.5*np.sqrt(
                        self._y_std[-1]/self._y_count[-1])
                    self._y_max[-1] = self._y_avg[-1] + 0.5*np.sqrt(
                        self._y_std[-1]/self._y_count[-1])
                    self._x[-1] += (this_x - self._x[-1]) / self._y_count[-1]
                else:
                    # If the number of data at a location is less than
                    # min_count, the data at this location will be discarded.
                    if self._y_count[-1] < self._min_count:
                        del self._x[-1]
                        del self._y_count[-1]
                        del self._y_avg[-1]
                        del self._y_min[-1]
                        del self._y_max[-1]
                        del self._y_std[-1]
                    self._x.append(this_x)
                    self._y_count.append(1)
                    self._y_avg.append(this_y)
                    self._y_min.append(this_y)
                    self._y_max.append(this_y)
                    self._y_std.append(0.0)
            else:
                self._x.append(this_x)
                self._y_count.append(1)
                self._y_avg.append(this_y)
                self._y_min.append(this_y)
                self._y_max.append(this_y)
                self._y_std.append(0.0)

        if len(self._x) > self.MAX_LENGTH:
            self.__delete__(instance)

    def __get__(self, instance, instance_type):
        if instance is None:
            return self

        y = self.DataStat()
        with self._lock:
            if self._y_count and self._y_count[-1] < self._min_count:
                x = np.array(self._x[:-1])
                y.count = np.array(self._y_count[:-1])
                y.avg = np.array(self._y_avg[:-1])
                y.min = np.array(self._y_min[:-1])
                y.max = np.array(self._y_max[:-1])
            else:
                x = np.array(self._x)
                y.count = np.array(self._y_count)
                y.avg = np.array(self._y_avg)
                y.min = np.array(self._y_min)
                y.max = np.array(self._y_max)

            info = copy.copy(self._info)

        return x, y, info

    def __delete__(self, instance):
        with self._lock:
            del self._x[0]
            del self._y_count[0]
            del self._y_avg[0]
            del self._y_min[0]
            del self._y_max[0]
            del self._y_std[0]

    def clear(self):
        with self._lock:
            self._x.clear()
            self._y_count.clear()
            self._y_avg.clear()
            self._y_min.clear()
            self._y_max.clear()
            self._y_std.clear()
        # do not clear _info here!


class AbstractData:
    @classmethod
    def clear(cls):
        for attr in cls.__dict__.values():
            if isinstance(attr, PairData):
                # descriptor protocol will not be triggered here
                attr.clear()


class MovingAverageArray:
    """Stores moving average of raw images."""
    def __init__(self):
        self._data = None  # moving average

        self._window = 1
        self._count = 0

    def __get__(self, instance, instance_type):
        if instance is None:
            return self

        return self._data

    def __set__(self, instance, data):
        self._validate_input(data)

        if self._data is not None and self._window > 1 and \
                self._count <= self._window and data.shape == self._data.shape:
            if self._count < self._window:
                self._count += 1
                self._data = xt_moving_average(self._data, data, self._count)
            else:  # self._count == self._window
                # here is an approximation
                self._data = xt_moving_average(self._data, data, self._count)

        else:
            self._data = data
            self._count = 1

    def _validate_input(self, data):
        if not isinstance(data, np.ndarray):
            raise TypeError(r"Input must be an numpy.ndarray!")

    @property
    def window(self):
        return self._window

    @window.setter
    def window(self, v):
        if not isinstance(v, int) or v <= 0:
            raise ValueError("Input must be integer")

        self._window = v

    @property
    def count(self):
        return self._count


class RawImageData(MovingAverageArray):
    """Stores moving average of raw images."""
    def __init__(self):
        super().__init__()

    def _validate_input(self, images):
        super()._validate_input(images)

        if images.ndim <= 1 or images.ndim > 3:
            raise ValueError(
                f"The shape of images must be (y, x) or (n_pulses, y, x)!")

    @property
    def n_images(self):
        if self._data is None:
            return 0

        if self._data.ndim == 3:
            return self._data.shape[0]
        return 1

    @property
    def pulse_resolved(self):
        return self._data.ndim == 3


class XgmData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = None
        self.intensity = 0.0


class XasData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # show the expected data type
        self.bin_center = np.array([])
        self.bin_count = np.array([])
        self.xgm = np.array([])
        self.absorptions = [np.array([]), np.array([])]

        self.reset =  False


class BinData(AbstractData):
    """Binning data model."""

    # 1D binning
    vec1_hist = None
    fom1_hist = None
    count1_hist = None
    vec2_hist = None
    fom2_hist = None
    count2_hist = None

    # 2D binning
    fom12_hist = None
    count12_hist = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.mode = None

        self.reset1 = False
        self.reset2 = False

        # shared between 1D binning and 2D binning:
        # 1. For 1D binning, they both are y coordinates;
        # 2. For 2D binning, center1 is the x coordinate and center2 is the
        #    y coordinate.
        self.n_bins1 = 0
        self.n_bins2 = 0
        self.center1 = None
        self.center2 = None

        self.label1 = None
        self.label2 = None

        self.iloc1 = -1
        self.fom1 = None
        self.vec1 = None
        self.iloc2 = -1
        self.fom2 = None
        self.vec2 = None

        self.vec_x = None
        self.vec_label = None

        self.fom12 = None

    def update_hist(self, tid=None):
        n1 = self.n_bins1
        n2 = self.n_bins2

        # reset and initialization
        if self.reset1:
            self.__class__.fom1_hist = np.zeros(n1, dtype=np.float32)
            self.__class__.count1_hist = np.zeros(n1, dtype=np.uint32)
            # Real initialization could take place later then valid vec
            # is received.
            self.__class__.vec1_hist = None

        if self.reset2:
            self.__class__.fom2_hist = np.zeros(n2, dtype=np.float32)
            self.__class__.count2_hist = np.zeros(n2, dtype=np.uint32)
            # Real initialization could take place later then valid vec
            # is received.
            self.__class__.vec2_hist = None

        if (self.reset1 or self.reset2) and n1 > 0 and n2 > 0:
            self.__class__.fom12_hist = np.zeros((n2, n1), dtype=np.float32)
            self.__class__.count12_hist = np.zeros((n2, n1), dtype=np.float32)

        # update history

        if 0 <= self.iloc1 < n1:
            self.__class__.count1_hist[self.iloc1] += 1
            self.__class__.fom1_hist[self.iloc1] = self.fom1

            if self.vec1 is not None:
                if self.vec1_hist is None or len(self.vec_x) != self.vec1_hist.shape[0]:
                    # initialization
                    self.__class__.vec1_hist = np.zeros(
                        (len(self.vec_x), n1), dtype=np.float32)

                self.__class__.vec1_hist[:, self.iloc1] = self.vec1

        if 0 <= self.iloc2 < n2:
            self.__class__.count2_hist[self.iloc2] += 1
            self.__class__.fom2_hist[self.iloc2] = self.fom2

            if self.vec2 is not None:
                if self.vec2_hist is None or len(self.vec_x) != self.vec2_hist.shape[0]:
                    # initialization
                    self.__class__.vec2_hist = np.zeros(
                        (len(self.vec_x), n2), dtype=np.float32)

                self.__class__.vec2_hist[:, self.iloc2] = self.vec2

        if 0 <= self.iloc1 < n1 and 0 <= self.iloc2 < n2:
            self.__class__.count12_hist[self.iloc2, self.iloc1] += 1
            self.__class__.fom12_hist[self.iloc2, self.iloc1] = self.fom12


class CorrelationData(AbstractData):
    """Correlation data model."""

    _n_params = len(config["CORRELATION_COLORS"])

    def __init__(self):
        super().__init__()
        self.fom = None
        for i in range(1, self._n_params+1):
            setattr(self, f"correlator{i}", None)

        self.reset = False

    def update_hist(self, tid=None):
        if self.reset:
            for i in range(1, self._n_params + 1):
                try:
                    self.__class__.__dict__[f"correlation{i}"].clear()
                except KeyError:
                    pass

        fom = self.fom
        for i in range(1, self._n_params+1):
            corr = getattr(self, f"correlator{i}")
            if corr is not None:
                setattr(self, f"correlation{i}", (corr, fom))


class RoiData(AbstractData):
    """A class which stores ROI data."""

    _n_rois = len(config["ROI_COLORS"])
    __initialized = False

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls, *args, **kwargs)
        # (sum/mean) histories of ROIs
        if not cls.__initialized:
            for i in range(1, cls._n_rois+1):
                setattr(cls, f"roi{i}_hist", PairData())
            cls.__initialized = True
        return instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(1, self._n_rois+1):
            setattr(self, f"roi{i}", None)  # (x, y, w, h)
            setattr(self, f"roi{i}_proj_x", None)  # projection on x
            setattr(self, f"roi{i}_proj_y", None)  # projection on y
            setattr(self, f"roi{i}_fom", None)  # FOM

        self.reset = False

    def update_hist(self, tid=None):
        if self.reset:
            for i in range(1, self._n_rois + 1):
                self.__class__.__dict__[f"roi{i}_hist"].clear()

        if tid is not None:
            for i in range(1, self._n_rois+1):
                fom = getattr(self, f"roi{i}_fom")
                if fom is None:
                    fom = 0
                setattr(self, f"roi{i}_hist", (tid, fom))


class AzimuthalIntegrationData(AbstractData):
    """Azimuthal integration data model.

    momentum (numpy.ndarray): azimuthal integration momentum.
        Shape = (integ_points,)
    intensities (list): azimuthal integration intensities for
        all individual pulse images in a train.
    intensities_fom (list): FOM of intensities.
    intensity (numpy.ndarray): azimuthal integration intensity for the
        average of all pulse images in a train. Shape = (intensity,)
    intensity_fom (float): FOM of intensity.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.momentum = None
        self.intensities = None
        self.intensities_foms = None
        self.intensity = None
        self.intensity_fom = None

        self.momentum_label = "Momentum transfer (1/A)"
        self.intensity_label = "Scattering signal (arb.u.)"


class PumpProbeData(AbstractData):
    """Pump-probe data model."""

    fom_hist = PairData()

    class MovingAverage:
        def __init__(self):
            self._x = None
            self._on_ma = None  # moving average of on data
            self._off_ma = None  # moving average of off data

            self._ma_window = 1
            self._ma_count = 0

            self._lock = Lock()

        def __get__(self, instance, instance_type):
            return self._x, self._on_ma, self._off_ma

        def __set__(self, instance, data):
            x, on, off = data

            with self._lock:
                # x is always None when on/off are image data
                if self._on_ma is not None and on.shape != self._on_ma.shape:
                    # reset moving average if data shape (ROI shape) changes
                    self._ma_count = 0
                    self._on_ma = None
                    self._off_ma = None

                self._x = x
                if self._ma_window > 1 and self._ma_count > 0:
                    if self._ma_count < self._ma_window:
                        self._ma_count += 1
                        denominator = self._ma_count
                    else:   # self._ma_count == self._ma_window
                        # here is an approximation
                        denominator = self._ma_window
                    self._on_ma += (on - self._on_ma) / denominator
                    self._off_ma += (off - self._off_ma) / denominator

                else:  # self._ma_window == 1
                    self._on_ma = on
                    self._off_ma = off
                    if self._ma_window > 1:
                        self._ma_count = 1  # 0 -> 1

        @property
        def moving_average_window(self):
            return self._ma_window

        @moving_average_window.setter
        def moving_average_window(self, v):
            if not isinstance(v, int) or v <= 0:
                v = 1

            if v < self._ma_window:
                # if the new window size is smaller than the current one,
                # we reset everything
                with self._lock:
                    self._ma_window = v
                    self._ma_count = 0
                    self._x = None
                    self._on_ma = None
                    self._off_ma = None

            self._ma_window = v

        @property
        def moving_average_count(self):
            return self._ma_count

        def clear(self):
            with self._lock:
                self._ma_window = 1
                self._ma_count = 0
                self._x = None
                self._on_ma = None
                self._off_ma = None

    # Moving average of the on/off data in pump-probe experiments, for
    # example: azimuthal integration / ROI / 1D projection, etc.
    data = MovingAverage()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.analysis_type = None

        self.abs_difference = None

        # the current average of on/off images
        self.on_image_mean = None
        self.off_image_mean = None

        # the current ROI of on/off images
        self.on_roi = None
        self.off_roi = None

        self.x = None
        # normalized on/off/on-off moving average
        self.norm_on_ma = None
        self.norm_off_ma = None
        self.norm_on_off_ma = None

        # FOM is defined as the difference of the FOMs between on and off
        # signals. For example, in azimuthal integration analysis, FOM is
        # the integration of the scattering curve; in ROI analysis, FOM is
        # the sum of ROI.
        self.fom = None

        self.reset = False

    def update_hist(self, tid=None):
        if self.reset:
            self.__class__.__dict__['data'].clear()
            self.__class__.__dict__['fom_hist'].clear()

        if tid is not None:
            fom = self.fom
            if fom is not None:
                self.fom_hist = (tid, fom)

    @property
    def ma_window(self):
        return self.__class__.__dict__['data'].moving_average_window

    @ma_window.setter
    def ma_window(self, v):
        self.__class__.__dict__['data'].moving_average_window = v

    @property
    def ma_count(self):
        return self.__class__.__dict__['data'].moving_average_count


class ImageData:
    """Image data model.

    ImageData is a container for storing self-consistent image data.
    Once constructed, the internal data are not allowed to be modified.

    Attributes:
        _images (list): a list of pulse images in the train. A value of
            None only indicates that the corresponding pulse image is
            not needed (in the main process).
        pixel_size (float): pixel size of the detector.
        n_images (int): number of images in the train.
        background (float): a uniform background value.
        ma_window (int): moving average window size.
        ma_count (int): current moving average count.
        threshold_mask (tuple): (lower, upper) boundaries of the
            threshold mask.
        mean (numpy.ndarray): average image over the train.
        masked_mean (numpy.ndarray): average image over the train with
            threshold mask applied.
        ref (numpy.ndarray): reference image.
        masked_ref (numpy.ndarray): reference image with threshold mask
            applied.
    """

    if 'IMAGE_DTYPE' in config:
        _DEFAULT_DTYPE = config['IMAGE_DTYPE']
    else:
        _DEFAULT_DTYPE = np.float32

    def __init__(self, data, *,
                 mean=None,
                 reference=None,
                 background=0.0,
                 image_mask=None,
                 threshold_mask=(-np.inf, np.inf),
                 ma_window=1,
                 ma_count=1,
                 keep=None):
        """Initialization.

        :param numpy.ndarray data: image data in a train.
        :param numpy.ndarray mean: nanmean of image data in a train. If not
            given, it will be calculated based on the image data. Only used
            for pulse-resolved detectors.
        :param numpy.ndarray reference: reference image.
        :param float background: a uniform background value.
        :param numpy.ndarray image_mask: image mask.
        :param tuple threshold_mask: threshold mask.
        :param int ma_window: moving average window size.
        :param int ma_count: current moving average count.
        :param None/list keep: pulse image indices to keep. None for
            keeping nothing.

        Note: data, reference and image_mask must not be modified in-place.
        """
        if not isinstance(data, np.ndarray):
            raise TypeError(r"Image data must be numpy.ndarray!")

        if data.ndim <= 1 or data.ndim > 3:
            raise ValueError(f"The shape of image data must be (y, x) or "
                             f"(n_pulses, y, x)!")

        self._pixel_size = config['PIXEL_SIZE']

        if data.dtype != self._DEFAULT_DTYPE:
            # FIXME: dtype of the incoming data could be integer, but integer
            #        array does not have nanmean.
            images = data.astype(self._DEFAULT_DTYPE)
        else:
            images = data

        self._shape = images.shape[-2:]

        if data.ndim == 3:
            if mean is None:
                self._mean = xt_nanmean_images(images)
            else:
                self._mean = mean

            self._n_images = images.shape[0]
            self._pulse_resolved = True

            # No matter 'keep' is None or a list, the interface for accessing a
            # single image is the same.
            if keep is None:
                # _images is an numpy.ndarray
                self._images = data
            else:
                if not isinstance(keep, (tuple, list)):
                    raise TypeError("'keep' must be a tuple or list!")
                # _images is a list of numpy.ndarray
                self._images = [None] * self._n_images

                for i in keep:
                    self._images[i] = data[i]
        else:
            # Note: _image is _mean for train-resolved detectors
            self._mean = images
            self._n_images = 1
            self._pulse_resolved = False

            self._images = []  # not used for train-resolved data

        self._threshold_mask = threshold_mask

        # if image_mask is given, we assume that the shape of the image
        # mask is the same as the image. This is guaranteed in
        # ImageProcessor.
        self._image_mask = image_mask

        # self._masked_mean does not share memory with self._mean
        self._masked_mean = self._mean.copy()
        mask_image(self._masked_mean,
                   threshold_mask=threshold_mask,
                   image_mask=image_mask,
                   inplace=True)

        self._ref = reference

        self._bkg = background

        self._ma_window = ma_window
        self._ma_count = ma_count

    @property
    def images(self):
        if self.pulse_resolved:
            return self._images
        return self._mean

    @property
    def reference(self):
        return self._ref

    @property
    def pixel_size(self):
        return self._pixel_size

    @property
    def n_images(self):
        return self._n_images

    @property
    def pulse_resolved(self):
        return self._pulse_resolved

    @property
    def shape(self):
        return self._shape

    @property
    def background(self):
        return self._bkg

    @property
    def ma_window(self):
        return self._ma_window

    @property
    def ma_count(self):
        return self._ma_count

    @property
    def threshold_mask(self):
        return self._threshold_mask

    @property
    def image_mask(self):
        return self._image_mask

    @property
    def mean(self):
        return self._mean

    @property
    def masked_mean(self):
        return self._masked_mean


class ProcessedData:
    """A class which stores the processed data.

    ProcessedData also provide interface for manipulating the other node
    dataset, e.g. RoiData, CorrelationData, PumpProbeData.

    Attributes:
        _tid (int): train ID.
        _image (ImageData): image data.
        xgm (XgmData): XGM data.
        ai (AzimuthalIntegrationData): azimuthal integration data.
        pp (PumpProbeData): pump-probe data.
        roi (RoiData): ROI data.
        correlation (CorrelationData): correlation related data.
        bin (BinData): binning data.
        xas (XasData): XAS data.
    """

    def __init__(self, tid, images, **kwargs):
        """Initialization."""
        self._tid = tid  # train ID

        self._image = ImageData(images, **kwargs)

        self.xgm = XgmData()

        self.ai = AzimuthalIntegrationData()
        self.pp = PumpProbeData()
        self.roi = RoiData()
        self.correlation = CorrelationData()
        self.bin = BinData()
        self.xas = XasData()

    @property
    def tid(self):
        return self._tid

    @property
    def image(self):
        return self._image

    @property
    def pulse_resolved(self):
        return self.image.pulse_resolved

    @property
    def n_pulses(self):
        return self._image.n_images

    def update(self):
        self.roi.update_hist(self._tid)
        self.pp.update_hist(self._tid)
        self.correlation.update_hist(self._tid)
        self.bin.update_hist(self._tid)


class DataManagerMixin:
    """Interface for manipulating data model."""
    @staticmethod
    def add_correlation(idx, device_id, ppt, resolution=0.0):
        """Add a correlation.

        :param int idx: index (starts from 1)
        :param str device_id: device ID
        :param str ppt: property
        :param float resolution: resolution. Default = 0.0
        """
        if idx <= 0:
            raise ValueError("Correlation index must start from 1!")

        if device_id and ppt:
            corr = f'correlation{idx}'
            if resolution:
                setattr(CorrelationData, corr, AccumulatedPairData(
                    device_id=device_id, property=ppt, resolution=resolution))
            else:
                setattr(CorrelationData, corr, PairData(
                    device_id=device_id, property=ppt))
        else:
            DataManagerMixin.remove_correlation(idx)

    @staticmethod
    def get_correlations():
        correlations = []
        for kls in CorrelationData.__dict__:
            if isinstance(CorrelationData.__dict__[kls], PairData):
                correlations.append(kls)
        return correlations

    @staticmethod
    def remove_correlation(idx):
        name = f'correlation{idx}'
        if hasattr(CorrelationData, name):
            delattr(CorrelationData, name)

    @staticmethod
    def remove_correlations():
        for i in range(CorrelationData._n_params):
            DataManagerMixin.remove_correlation(i+1)
