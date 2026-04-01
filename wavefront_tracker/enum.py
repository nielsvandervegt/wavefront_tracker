from enum import Enum


class Direction(Enum):
    """
    Direction of the wavefront
    E.g. in case of overtopping: crest to toe
    """
    LEFT_TO_RIGHT = 0
    RIGHT_TO_LEFT = 1
    TOP_TO_BOTTOM = 2
    BOTTOM_TO_TOP = 3
