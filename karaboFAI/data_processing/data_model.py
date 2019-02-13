"""
Offline and online data analysis and visualization tool for azimuthal
integration of different data acquired with various detectors at
European XFEL.

Data models for analysis and visualization.

Author: Jun Zhu <jun.zhu@xfel.eu>
Copyright (C) European X-Ray Free-Electron Laser Facility GmbH.
All rights reserved.
"""
import abc
from enum import IntEnum

import numpy as np
from cached_property import cached_property

from ..logger import logger
from .proc_utils import nanmean_axis0_para


class DataSource(IntEnum):
    CALIBRATED_FILE = 0  # calibrated data from files
    CALIBRATED = 1  # calibrated data from Karabo-bridge
    PROCESSED = 2  # processed data from the Middle-layer device


class OpLaserMode(IntEnum):
    INACTIVE = 0  # not perform any relevant calculation
    NORMAL = 1  # on-/off- pulses in the same train
    EVEN_ON = 2  # on-/off- pulses have even/odd train IDs, respectively
    ODD_ON = 3  # on/-off- pulses have odd/even train IDs, respectively


class FomName(IntEnum):
    # Calculate the FOM based on the azimuthal integration of the mean
    # of the assembled image(s).
    ASSEMBLED_MEAN = 1
    # Calculate the FOM based on the difference between the azimuthal
    # integration result between the laser on/off pulse(s).
    LASER_ON_OFF = 2


class AiNormalizer(IntEnum):
    # Normalize the azimuthal integration curve by integration of the
    # curve itself.
    CURVE = 1
    # Normalize the azimuthal integration curve by the sum of the
    # integrations of the ROI(s).
    ROI = 2


class RoiValueType(IntEnum):
    INTEGRATION = 1  # monitor integration of ROI
    MEAN = 2  # monitor mean of ROI


class TrainData:
    MAX_LENGTH = 1000000

    def __init__(self, **kwargs):
        # x can be tid or a correlated param

        # We need to have a 'x' for each sub-dataset due to the
        # concurrency of data processing.
        self._x = []
        self._values = []
        self._info = kwargs

    def __get__(self, instance, instance_type):
        if instance is None:
            return self
        return self._x, self._values, self._info

    def __set__(self, instance, pair):
        x, value = pair
        self._x.append(x)
        self._values.append(value)

        # TODO: improve, e.g., cache
        if len(self._x) > self.MAX_LENGTH:
            self.__delete__(instance)

    def __delete__(self, instance):
        del self._x[0]
        del self._values[0]

    def clear(self):
        self._x.clear()
        self._values.clear()


class AbstractData(abc.ABC):

    @classmethod
    def clear(cls):
        for kls in cls.__dict__:
            if isinstance(cls.__dict__[kls], TrainData):
                # descriptor protocol will not be triggered here
                cls.__dict__[kls].clear()


class RoiData(AbstractData):
    """A class which stores ROI data."""

    # value (integration/mean/median) histories of ROI1 and ROI2
    values1 = TrainData()
    values2 = TrainData()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.roi1 = None  # (w, h, px, py)
        self.roi2 = None  # (w, h, px, py)


class LaserOnOffData(AbstractData):
    """A class which stores Laser on-off data."""

    # FOM history
    foms = TrainData()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_pulse = None
        self.off_pulse = None
        self.diff = None


class CorrelationData(AbstractData):
    """A class which stores Laser on-off data."""

    @classmethod
    def add_param(cls, idx, device_id, ppt):
        setattr(cls, f'param{idx}', TrainData(device_id=device_id,
                                              property=ppt))

    @classmethod
    def remove_param(cls, idx):
        name = f'param{idx}'
        if hasattr(cls, name):
            delattr(cls, name)

    @classmethod
    def get_params(cls):
        params = []
        for kls in cls.__dict__:
            if isinstance(cls.__dict__[kls], TrainData):
                params.append(kls)

        return params


class ImageData:
    """A class that manages the detector images.

    Attributes:
        _images (numpy.ndarray): detector images for all the pulses in
            a train. shape = (pulse_id, y, x) for pulse-resolved
            detectors and shape = (y, x) for train-resolved detectors.
        _threshold_mask (tuple): (min, max) threshold of the pixel value.
        _image_mask (numpy.ndarray): an image mask, default = None.
            Shape = (y, x)
        _crop_area (tuple): (w, h, x, y) of the cropped image.
    """
    def __init__(self, images, *,
                 threshold_mask=None,
                 image_mask=None,
                 background_level=None,
                 crop_area=None):
        """Initialization."""
        self._images = images
        self._bkg = background_level
        if images is not None:
            self._images -= background_level
        self._crop_area = crop_area

        # the mask information is stored in the data so that all the
        # processing and visualization can use the same mask
        self._threshold_mask = threshold_mask
        self._image_mask = image_mask

    @cached_property
    def n_images(self):
        if self._images is None:
            return 0
        if self._images.ndim == 3:
            return self._images.shape[0]
        return 1

    @property
    def threshold_mask(self):
        return self._threshold_mask

    @cached_property
    def image_mask(self):
        if self._image_mask is None:
            image_mask = np.zeros_like(self.mean_image, dtype=np.uint8)
        else:
            if self.image_mask.shape != self.mean_image.shape:
                print("Invalid mask shape {} for image with shape {}".
                      format(self._image_mask.shape, self.mean_image.shape))

            image_mask = self.image_mask

        return image_mask

    @cached_property
    def mean_image(self):
        """Average of the detector images over pulses in a train.

        :return numpy.ndarray: a single image, shape = (y, x)
        """
        if self._images.ndim == 3:
            # pulse resolved
            return nanmean_axis0_para(self.images,
                                      max_workers=8, chunk_size=20)
        # train resolved
        return self.images

    @cached_property
    def masked_mean_image(self):
        # keep both mean image and masked mean image so that we can
        # recalculate the masked image
        mean_image = np.copy(self.mean_image)

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

    @cached_property
    def images(self):
        """Return the cropped image.

        Warning: it shares the memory space with self._images
        """
        if self._crop_area is None:
            return self._images

        w, h, x, y = self._crop_area
        return self._images[..., y:y+h, x:x+w]


class ProcessedData:
    """A class which stores the processed data.

    ProcessedData also provide interface for manipulating the other node
    dataset, e.g. RoiData, CorrelationData, LaserOnOffData.

    Attributes:
        tid (int): train ID.
        momentum (numpy.ndarray): x-axis of azimuthal integration result.
            Shape = (momentum,)
        intensities (numpy.ndarray): y-axis of azimuthal integration result.
            Shape = (pulse_id, intensity)
        intensity_mean (numpy.ndarray): average of the y-axis of azimuthal
            integration result over pulses. Shape = (intensity,)
        roi (RoiData): stores ROI related data.
        on_off (LaserOnOffData): stores laser on-off related data.
        correlation (CorrelationData): correlation related data.
    """

    def __init__(self, tid, images=None, **kwargs):
        """Initialization."""
        if not isinstance(tid, int):
            raise ValueError("Train ID must be an integer!")

        self._tid = tid  # current Train ID
        if images is None:
            self._image_data = None
        else:
            self._image_data = ImageData(images, **kwargs)

        self.momentum = None
        self.intensities = None
        self.intensity_mean = None

        self.roi = RoiData()
        self.on_off = LaserOnOffData()
        self.correlation = CorrelationData()

    @property
    def tid(self):
        return self._tid

    @property
    def image(self):
        return self._image_data

    @classmethod
    def clear_roi_hist(cls):
        RoiData.clear()

    @classmethod
    def clear_onoff_hist(cls):
        LaserOnOffData.clear()

    @classmethod
    def clear_correlation_hist(cls):
        CorrelationData.clear()

    @staticmethod
    def add_correlator(idx, device_id, ppt):
        """Add a correlated parameter.

        :param int idx: index
        :param str device_id: device ID
        :param str ppt: property
        """
        if device_id and ppt:
            CorrelationData.add_param(idx, device_id, ppt)
        else:
            CorrelationData.remove_param(idx)

    @staticmethod
    def get_correlators():
        return CorrelationData.get_params()

    def empty(self):
        """Check the goodness of the data."""
        logger.debug("Deprecated! Check the specific data!")
        if self.image is None:
            return True
        return False


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
