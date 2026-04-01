import cv2
import numpy as np
import pandas as pd

from pathlib import Path

from .enum import Direction


class Video:
    """
    Base class containing all information required to run wft
    """
    # Direction of the wavefront
    direction: Direction

    def __init__(self, path: str | Path, mp4: list[str] | str, reference_points: str | Path, volume_time: str | Path, slow_down: float = 1.0, dont_track: str | Path = None) -> None:
        """
        Constructor to create the Video object and check user input

        Parameters
        ----------
        path: list[str] | str
            Path to the folder containing the mp4 files to analyse
        mp4: list[str] | str
            mp4 files in path to analyse
        reference_points: str | Path
            Path to a PNG file of starting frame with reference points indicated, see note.
        volume_time: str | Path
            Path to an Excel file with event number, mp4 filename, the volume and the timestamp in seconds, see note.
        slow_down: float
            How often the footage is slowed down (default: 1x)
        dont_track: str | Path
            Image with areas (people/objects) which wont be used for drone tracking

        Note
        ----
        reference_points:
            Path to a PNG indicating all reference points by a red pixel. The rest of the frame should be transparant,
            indicate with a green pixel the crest and with a blue pixel the toe.
        volume_time:
            Path to an Excel file with a event number, mp4 filename, the volume and the timestamp when the volume is
            released (see below). When analysing multiple mp4 files, take note that the timestamp is relative for the
            respective mp4 file. Use columns: 'eventnr', 'mp4_file', 'volume', and 'seconds'. Use eventnr ascending
            starting from 1.
            [[1, "DJI_0680.MP4", 1_000, 62], [2, "DJI_0681.MP4", 1_250, 4]]
        """
        # Save parameters
        self.path = path
        self.mp4 = mp4
        self.reference_points = reference_points
        self.volume_time = volume_time
        self.slow_down = slow_down
        self.dont_track = dont_track

        # Check if path is Path object
        if not isinstance(path, Path):
            self.path = Path(path)

        # Convert mp4 files from non-list to list if needed
        if not isinstance(mp4, list | np.ndarray):
            self.mp4 = [mp4]

        # Check if all mp4 exists
        self.__check_given_paths()

        # Convert reference points
        self.__convert_reference_points()

        # Load volume time
        self.__load_volume_time_excel()

    def __check_given_paths(self) -> None:
        """
        Check if the given paths exists
        """
        # Check if each given path exists
        for mp4_file in self.mp4:

            # Check if the path exists
            if not Path(self.path / mp4_file).exists():
                raise FileNotFoundError(f"[ERROR] Not found: {Path(self.path / mp4_file)}")

    def __convert_reference_points(self) -> None:
        """
        Load the (x,y) of the pairs of reference points in a frame
        """
        # Load PNG
        init_png = cv2.imread(str(self.path / self.reference_points))

        # Collect colored pixels (x, y, and which color (0 = toe, 1 = crest, 2 = ref point))
        y, x, col = np.where(init_png == 255)

        # Determine direction
        x_toe, y_toe = float(x[col == 0]), float(y[col == 0])
        x_crest, y_crest = float(x[col == 1]), float(y[col == 1])
        if np.abs(x_toe - x_crest) > np.abs(y_toe - y_crest):
            if x_toe > x_crest:
                self.direction = Direction.LEFT_TO_RIGHT
            else:
                self.direction = Direction.RIGHT_TO_LEFT
        else:
            if y_toe > y_crest:
                self.direction = Direction.TOP_TO_BOTTOM
            else:
                self.direction = Direction.BOTTOM_TO_TOP

        # Collect reference points
        ref_points = np.array([x[col == 2], y[col == 2]]).T
        sort_axis = 0 if self.direction in [Direction.LEFT_TO_RIGHT, Direction.RIGHT_TO_LEFT] else 1
        ref_points = ref_points[ref_points[:, sort_axis].argsort()]
        if self.direction in [Direction.RIGHT_TO_LEFT, Direction.BOTTOM_TO_TOP]:
            ref_points = ref_points[::-1]

        # Reshape to an array of (pairs, points [0, 1], coordinate [0, 1])
        if len(ref_points) % 2 != 0:
            raise ValueError("[ERROR] Uneven pair of reference points!")
        self.reference_points = ref_points.reshape(int(len(ref_points) / 2), 2, 2)

    def __load_volume_time_excel(self) -> None:
        """
        Read the volume time Excel
        """
        # Load into a dataframe
        df = pd.read_excel(self.path / self.volume_time)

        # Check if the right columns are present
        if not all(column in df.columns for column in ["eventnr", "mp4_file", "volume", "seconds"]):
            raise ValueError("[ERROR] Columns 'eventnr', 'mp4_file', 'volume', and 'seconds' not present in the Excel.")

        # Only take the necessary columns
        self.volume_time = df[["eventnr", "mp4_file", "volume", "seconds"]]
        self.volume_time.set_index("eventnr", inplace=True)
