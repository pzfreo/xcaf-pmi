"""Specify's manufacturing process UDA and its XCAF named data keys."""

OPTIONS = ("machined", "3D printed: FDM", "3D printed: resin", "3D printed: powder",
           "3D printed: metal", "sheet metal", "moulded", "cast")
KEY = "manufacturing_process"
DEFAULT = "default.manufacturing_process"


def process_key(key: str) -> str:
    return key.lower().replace(" ", "").replace("-", "").replace("_", "")


def process_value(value: str | None) -> str | None:
    return next((option for option in OPTIONS if value is not None and option.lower() == value.lower()), None)
