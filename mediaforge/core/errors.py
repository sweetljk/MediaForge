class ConversionError(Exception):
    """An actionable error suitable for showing in the desktop interface."""


class CancelledError(ConversionError):
    pass


class SkipError(ConversionError):
    pass
