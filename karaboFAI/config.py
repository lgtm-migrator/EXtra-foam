import os


class Config:
    # distance sample - detector plan (orthogonal distance, not along the
    # beam), in meter
    DIST = 0.2
    # coordinate of the point of normal incidence along the detector's first
    # dimension, in pixels
    CENTER_Y = 620
    # coordinate of the point of normal incidence along the detector's second
    # dimension, in pixels
    CENTER_X = 580
    PIXEL_SIZE = 0.5e-3  # in meter

    PHOTON_ENERGY = 9.30  # in, keV

    # 'full_csr" crashes the app
    INTEGRATION_METHODS = ['BBox', 'numpy', 'cython', 'splitpixel', 'lut',
                           'csr', 'nosplit_csr', 'lut_ocl', 'csr_ocl']

    LASER_MODES = {
        "normal": "Laser-on/off pulses in the same train",
        "even/odd": "Laser-on/off pulses in even/odd train",
        "odd/even": "Laser-on/off pulses in odd/even train"
    }

    # the lower and upper range of the radial unit
    INTEGRATION_RANGE = (0.2, 5)
    INTEGRATION_POINTS = 512  # number of points in the output pattern

    # *********************************************************************
    MAX_QUEUE_SIZE = 2

    # *********************************************************************
    UPDATE_FREQUENCY = 10  # in Hz

    MAIN_WINDOW_HEIGHT = 1000
    MAIN_WINDOW_WIDTH = 1380
    MAIN_LINE_PLOT_HEIGHT = 480

    MAX_LOGGING = 1000
    LOGGER_FONT_SIZE = 12

    MASK_RANGE = (0, 2500)  # image pixels beyond this range will be masked

    COLOR_MAP = "flame"

    TIMEOUT = 5  # timeout in data pipeline

    # FXE specific

    SOURCE = "FXE_DET_LPD1M-1/CAL/APPEND_CORRECTED"

    # The following is valid-ish for the 20180318 geometry
    QUAD_POSITIONS = [(-13.0, -299.0), (11.0, -8.0), (-254.0, 16.0), (-278.0, -275.0)]

    DEFAULT_SERVER_ADDR = "10.253.0.53"
    DEFAULT_SERVER_PORT = "4501"

    # DEFAULT_SERVER_ADDR = "localhost"
    # DEFAULT_SERVER_PORT = "12345"

    DEFAULT_GEOMETRY_FILE = os.path.join(os.path.expanduser("~"),
                                         "fxe-data/lpd_mar_18.h5")

    # *********************************************************************
    DEFAULT_FILE_SERVER_PORT = "12345"
    DEFAULT_FILE_SERVER_FOLDER = os.path.join(os.path.expanduser("~"),
                                              "fxe-data/r0078")