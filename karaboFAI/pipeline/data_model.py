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

from cached_property import cached_property

from ..algorithms import nanmean_axis0_para
from ..logger import logger
from ..config import config


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


class XgmData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = None
        self.intensity = 0.0


class MonoData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = None
        self.energy = 0.0


class XasData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # show the expected data type
        self.bin_center = np.array([])
        self.bin_count = np.array([])
        self.xgm = np.array([])
        self.absorptions = [np.array([]), np.array([])]


class BinData(AbstractData):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.analysis_type = None
        self.counts_x = None
        self.counts_y = None
        self.centers_x = None
        self.centers_y = None
        self.x = None
        self.y = None
        self.values = None


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

    def update_hist(self, tid):
        for i in range(1, self._n_rois+1):
            fom = getattr(self, f"roi{i}_fom")
            if fom is None:
                fom = 0
            setattr(self, f"roi{i}_hist", (tid, fom))


class AzimuthalIntegrationData(AbstractData):
    """Azimuthal integration data model."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.momentum = None
        self.intensities = None
        self.intensity_mean = None
        self.pulse_fom = None


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

        def reset(self):
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

    def update_hist(self, tid):
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

    @classmethod
    def clear(cls):
        super().clear()
        cls.__dict__['data'].reset()


class CorrelationData(AbstractData):
    """Correlation data model."""

    n_params = len(config["CORRELATION_COLORS"])

    def __init__(self):
        super().__init__()
        self.fom = None
        for i in range(1, self.n_params+1):
            setattr(self, f"correlator{i}", None)

    def update_hist(self, tid):
        fom = self.fom
        for i in range(1, self.n_params+1):
            corr = getattr(self, f"correlator{i}")
            if corr is not None:
                setattr(self, f"correlation{i}", (corr, fom))


class ImageData:
    """Image data model.

    Operation flow:

    remove background -> calculate mean image -> apply mask

    Attributes:
        pixel_size (float): detector pixel size.
        _images (numpy.ndarray): detector images for all the pulses in
            a train. shape = (pulse_index, y, x) for pulse-resolved
            detectors and shape = (y, x) for train-resolved detectors.
        _threshold_mask (tuple): (min, max) threshold of the pixel value.
    """
    class RawImage:
        def __init__(self):
            self._images = None  # moving average (original data)
            self._ma_window = 1
            self._ma_count = 0

            self._bkg = 0.0  # current background value

        def _invalid_image_cached(self):
            try:
                del self.__dict__['images']
            except KeyError:
                pass

        @property
        def background(self):
            return self._bkg

        @background.setter
        def background(self, v):
            if self._bkg != v:
                self._bkg = v
                self._invalid_image_cached()

        @cached_property
        def images(self):
            if self._images is None:
                return None
            # return a new constructed array
            return self._images - self._bkg

        def set(self, imgs):
            """Set new image data."""
            if self._images is not None and self._ma_window > 1:
                if imgs.shape != self._images.shape:
                    logger.error(
                        f"The shape {imgs.shape} of the new image is "
                        f"different from the current one "
                        f"{self._images.shape}!")
                    return

                if self._ma_count < self._ma_window:
                    self._ma_count += 1
                    self._images += (imgs - self._images) / self._ma_count
                else:  # self._ma_count == self._ma_window
                    # here is an approximation
                    self._images += (imgs - self._images) / self._ma_window

            else:  # self._images is None or self._ma_window == 1
                self._images = imgs
                self._ma_count = 1

            self._invalid_image_cached()

        @property
        def moving_average_window(self):
            return self._ma_window

        @moving_average_window.setter
        def moving_average_window(self, v):
            if not isinstance(v, int) or v <= 0:
                v = 1

            if v < self._ma_window:
                # if the new window size is smaller than the current one,
                # we reset the original image sum and count
                self._ma_window = v
                self._ma_count = 0
                self._images = None
                self._invalid_image_cached()

            self._ma_window = v

        @property
        def moving_average_count(self):
            return self._ma_count

        def clear(self):
            self._images = None
            self._ma_window = 1
            self._ma_count = 0
            self._bkg = 0.0

    class ImageRef:
        def __init__(self):
            self._image = None

        def __get__(self, instance, instance_type):
            if instance is None:
                return self
            return self._image

        def __set__(self, instance, value):
            self._image = value

        def __delete__(self, instance):
            self._image = None

    class ThresholdMask:
        def __init__(self, lb=None, ub=None):
            self._lower = lb
            self._upper = ub
            self._initialized = False

        def __get__(self, instance, instance_type):
            if instance is None:
                return self
            lower = -np.inf if self._lower is None else self._lower
            upper = np.inf if self._upper is None else self._upper
            return lower, upper

        def __set__(self, instance, value):
            self._lower = value[0]
            self._upper = value[1]
            self._initialized = True

        def __delete__(self, instance):
            self._lower = None
            self._upper = None
            self._initialized = False

        def initialized(self):
            return self._initialized

    __raw = RawImage()
    __ref = ImageRef()
    __threshold_mask = ThresholdMask()

    pixel_size = None

    def __init__(self, images):
        """Initialization."""
        if self.pixel_size is None:
            self.__class__.pixel_size = config["PIXEL_SIZE"]

        if not isinstance(images, np.ndarray):
            raise TypeError(r"Images must be numpy.ndarray!")

        if images.ndim <= 1 or images.ndim > 3:
            raise ValueError(
                f"The shape of images must be (y, x) or (n_pulses, y, x)!")

        if not self.__class__.__threshold_mask.initialized():
            self.__threshold_mask = config['MASK_RANGE']

        # update moving average
        self._set_images(images)

        # Instance attributes should be "frozen" after created. Otherwise,
        # the data used in different plot widgets could be different.
        self._images = self.__raw.images
        self._image_ref = self.__ref
        self._threshold_mask = self.__threshold_mask

        # cache these two properties
        self.ma_window
        self.ma_count

        self._registered_ops = set()

    @property
    def n_images(self):
        if self._images.ndim == 3:
            return self._images.shape[0]
        return 1

    def pulse_resolved(self):
        return self._images.ndim == 3

    @property
    def shape(self):
        return self._images.shape[-2:]

    @property
    def background(self):
        return self.__raw.background

    @property
    def threshold_mask(self):
        return self._threshold_mask

    @cached_property
    def ma_window(self):
        # Updating ma_window could set __raw._images to None. Since there
        # is no cache being deleted. '_images' in this instance will not
        # be set to None. Note: '_images' is not allowed to be None.
        return self.__raw.moving_average_window

    @cached_property
    def ma_count(self):
        # Updating ma_window could reset ma_count. Therefore, 'ma_count'
        # should both be a cached property
        return self.__raw.moving_average_count

    def _set_images(self, imgs):
        self.__raw.set(imgs)

    def set_ma_window(self, v):
        self.__raw.moving_average_window = v

    def set_background(self, v):
        self.__raw.background = v
        self._registered_ops.add("background")

    def set_threshold_mask(self, lb, ub):
        self.__threshold_mask = (lb, ub)
        self._registered_ops.add("threshold_mask")

    def set_reference(self):
        # Reference should be a copy of mean since mean could be modified
        # after a reference was set.
        self.__ref = np.copy(self.mean)
        self._registered_ops.add("reference")

    def remove_reference(self):
        self.__ref = None

        self._registered_ops.add("reference")

    @cached_property
    def images(self):
        """Return the background-subtracted images.

        Warning: it shares the memory space with self._images
        """
        return self._images

    @cached_property
    def ref(self):
        if self._image_ref is None:
            return None

        return self._image_ref

    @cached_property
    def masked_ref(self):
        if self.ref is None:
            return None
        return self._masked_mean_imp(np.copy(self.ref))

    @cached_property
    def mean(self):
        """Return the average of images over pulses in a train.

        The image is background-subtracted.

        :return numpy.ndarray: a single image, shape = (y, x)
        """
        return self._mean_imp(self.images)

    def _mean_imp(self, imgs):
        """Return the average of a stack of images."""
        if imgs.ndim == 3:
            # pulse resolved
            return nanmean_axis0_para(imgs, max_workers=8, chunk_size=20)
        # train resolved
        return imgs

    @cached_property
    def masked_mean(self):
        """Return the masked average image.

        The image is background-subtracted before applying the mask.
        """
        # keep both mean image and masked mean image so that we can
        # recalculate the masked image
        return self._masked_mean_imp(np.copy(self.mean))

    def _masked_mean_imp(self, mean_image):
        # Convert 'nan' to '-inf' and it will later be converted to the
        # lower range of mask, which is usually 0.
        # We do not convert 'nan' to 0 because: if the lower range of
        # mask is a negative value, 0 will be converted to a value
        # between 0 and 255 later.
        mean_image[np.isnan(mean_image)] = -np.inf
        # clip the array, which now will contain only numerical values
        # within the mask range
        np.clip(mean_image, *self._threshold_mask, out=mean_image)

        return mean_image

    def sliced_masked_mean(self, indices):
        """Get masked mean by indices of images.

        :param list indices: a list of integers.
        """
        imgs = self.images

        if imgs.ndim == 3:
            sliced_imgs = imgs[indices]
        else:
            if len(indices) > 1 or indices[0] != 0:
                raise IndexError(
                    f"{indices} is out of bound for train-resolved image data")
            sliced_imgs = imgs

        return self._masked_mean_imp(self._mean_imp(sliced_imgs))

    def update(self):
        invalid_caches = set()
        if "background" in self._registered_ops:
            self._images = self.__raw.images
            invalid_caches.update({"images", "mean", "masked_mean"})
        if "threshold_mask" in self._registered_ops:
            self._threshold_mask = self.__threshold_mask
            invalid_caches.update({"masked_mean", "masked_ref"})
        if "reference" in self._registered_ops:
            self._image_ref = self.__ref
            invalid_caches.update({"ref", "masked_ref"})

        for cache in invalid_caches:
            try:
                del self.__dict__[cache]
            except KeyError:
                pass

        self._registered_ops.clear()

    @classmethod
    def clear(cls):
        """Reset all the class attributes.

        Used in unittest only.
        """
        cls.__raw.clear()
        cls.__ref.__delete__(None)
        cls.__threshold_mask.__delete__(None)


class ProcessedData:
    """A class which stores the processed data.

    ProcessedData also provide interface for manipulating the other node
    dataset, e.g. RoiData, CorrelationData, PumpProbeData.

    Attributes:
        tid (int): train ID.
        momentum (numpy.ndarray): x-axis of azimuthal integration result.
            Shape = (momentum,)
        intensities (numpy.ndarray): y-axis of azimuthal integration result.
            Shape = (pulse_index, intensity)
        intensity_mean (numpy.ndarray): average of the y-axis of azimuthal
            integration result over pulses. Shape = (intensity,)
        roi (RoiData): stores ROI related data.
        pp (PumpProbeData): stores laser on-off related data.
        correlation (CorrelationData): correlation related data.
    """

    def __init__(self, tid, images=None):
        """Initialization."""
        self._tid = tid  # current Train ID

        if images is None:
            self._image_data = None
        else:
            self._image_data = ImageData(images)

        self.ai = AzimuthalIntegrationData()
        self.pp = PumpProbeData()
        self.xas = XasData()
        self.roi = RoiData()
        self.correlation = CorrelationData()
        self.bin = BinData()

        self.xgm = XgmData()
        self.mono = MonoData()

    @property
    def tid(self):
        return self._tid

    @property
    def image(self):
        return self._image_data

    @property
    def n_pulses(self):
        if self._image_data is None:
            return 0

        return self._image_data.n_images

    def empty(self):
        """Check the goodness of the data."""
        logger.debug("Deprecated! use self.n_pulses!")
        if self.image is None:
            return True
        return False

    def update_hist(self):
        self.roi.update_hist(self._tid)
        self.pp.update_hist(self._tid)
        self.correlation.update_hist(self._tid)


class Data4Visualization:
    """Data shared between all the windows and widgets.

    The internal data is only modified in MainGUI.updateAll()
    """
    def __init__(self):
        self.__value = ProcessedData(-1)

    def get(self):
        return self.__value

    def set(self, value):
        self.__value = value


class DataManager:
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
            DataManager.remove_correlation(idx)

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
        for i in range(CorrelationData.n_params):
            DataManager.remove_correlation(i+1)

    @staticmethod
    def reset_correlation():
        CorrelationData.clear()

    @staticmethod
    def reset_roi():
        RoiData.clear()

    @staticmethod
    def reset_pp():
        PumpProbeData.clear()

    @staticmethod
    def reset_xas():
        XasData.clear()
