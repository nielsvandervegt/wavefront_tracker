import cv2
import numpy as np
import os
import pandas as pd

from datetime import datetime
from pathlib import Path
from scipy.stats import trim_mean

from .enum import Direction
from .video import Video


class Analyse:
    """
    Object to conduct the analysis on the wavefront along a slope
    """
    # Undefined objects
    video: Video
    image_buffer: int
    track: bool
    tracking_buffer: int
    tracking_points_max: int
    moving_objects_trim: float
    grid_points_length: int
    grid_points_width: int


    def __init__(self, video: Video, timesteps_in_timeblock: int = 100, track: bool = True):
        """
        Constructor for the analyse object
        """
        self.video = video
        self.timesteps_in_timeblock = timesteps_in_timeblock
        self.track = track
        self.image_buffer = 15  # About FPS / 4
        self.tracking_buffer = 100  # About 5% of the resolution (~50 - 100 pixels)
        self.tracking_points_max = 1000
        self.moving_objects_trim = 0.1  # When moving objects are within the footage (e.g. a flag, people)
        self.grid_points_length = 10
        self.grid_points_width = 9
        self.output_folder = "raw_output"
    

    def start(self, force_restart: bool = False):
        """
        Init from start
        """
        # Check if there exists an output folder
        if Path(self.video.path / self.output_folder).exists() and not force_restart:
            
            # Check: overwrite existing output?
            print("[WARNING] Existing output found, do you want to restart the analysis?")
            inp = input("Overwrite existing data (Y/N): ")
            if inp.lower() != "y":
                print("Simulation aborted")
                return

        # Determine the current timeblock
        self.current_timeblock = 0

        # Determine list of mp4 files and start of frame
        self.mp4_files = self.video.mp4
        self.start_frame = 0
        
        # Reference points from Video object
        self.ref_points = np.array(self.video.reference_points, dtype=np.float64)

        # Init buffer
        cap = cv2.VideoCapture(str(self.video.path / self.mp4_files[0]))
        _, old_frame = cap.read()
        old_gray = cv2.cvtColor(old_frame, cv2.COLOR_BGR2GRAY)
        self.graybuffer = np.array([old_gray] * self.image_buffer)

        # Create a mask at the top and bottom of the video (avoiding the experiment)
        mask1 = np.zeros_like(old_gray)
        mask2 = np.zeros_like(old_gray)

        # Horizontal
        if self.video.direction in [Direction.LEFT_TO_RIGHT, Direction.RIGHT_TO_LEFT]:
            mask1[:int(np.min(self.ref_points[:, :, 1].flatten()) - self.image_buffer), :] = 255
            mask2[int(np.max(self.ref_points[:, :, 1].flatten()) + self.image_buffer):, :] = 255
        else:
            raise NotImplementedError()

        # Combine
        combined_mask = cv2.bitwise_or(mask1, mask2)

        # If there is a dont track image
        if self.video.dont_track is not None:
            mask3 = cv2.imread(str(self.video.path / self.video.dont_track))
            mask3 = cv2.cvtColor(mask3, cv2.COLOR_BGR2GRAY)
            filter = np.where(mask3 > 0)
            combined_mask[filter] = 0

        # Find the first set of tracking points
        if self.track:
            feature_params = dict(maxCorners=self.tracking_points_max, qualityLevel=0.1, minDistance=7, blockSize=7)
            self.p_0 = cv2.goodFeaturesToTrack(old_gray, mask=combined_mask, **feature_params)

        # Start analysis
        self.__run()
    

    def resume(self):
        # Check if there exists an output folder
        if not Path(self.video.path / self.output_folder).exists():

            # If there is no output folder
            print("[WARNING] No folder with output found. Start from beginning")
            self.start()
        
        # Determine the current timeblock (last with buffer)
        folders = np.sort([f for f in os.listdir(self.video.path / self.output_folder) if f.lower().startswith("timeblock_")])[::-1]
        for folder in folders:
            if os.path.exists(self.video.path / self.output_folder / folder / "buffer"):
                break
        
        # Determine the current timeblock
        self.current_timeblock = int(folder.split("_")[1]) + 1

        # Determine list of mp4 files and start of frame
        path_last_tb = self.video.path / self.output_folder / folder
        last_mp4 = pd.read_excel(path_last_tb / "frames.xlsx")["mp4_file"].to_numpy()[-1]

        self.mp4_files = self.video.mp4[self.video.mp4.index(last_mp4):]
        self.start_frame = self.current_timeblock * self.timesteps_in_timeblock

        # Init buffer
        buffersize = len(os.listdir(path_last_tb / "buffer"))
        if buffersize != self.image_buffer:
            raise ValueError(f"[ERROR] Buffersize mismatch (image_buffer = {self.image_buffer}; found {buffersize})")
        self.graybuffer = [cv2.imread(str(path_last_tb / "buffer" / f"buffer{n}.png"), cv2.IMREAD_GRAYSCALE) for n in range(self.image_buffer)]
        
        # Read tracking points
        if self.track:
            self.p_0 = pd.read_excel(path_last_tb / "tracking_points.xlsx", usecols = ["X", "Y"]).to_numpy()
            self.p_0 = np.array(self.p_0, dtype=np.float32)
            self.p_0 = self.p_0.reshape((len(self.p_0), 1, 2))

        # Reference points from last timestep
        self.ref_points = pd.read_excel(path_last_tb / "reference_points.xlsx", usecols = ["X0", "Y0", "X1", "Y1"]).to_numpy()
        self.ref_points = self.ref_points.reshape((len(self.ref_points), 2, 2))

        # Run
        print(f"[INFO] Resume at timeblock {self.current_timeblock}")
        self.__run()


    def __run(self) -> None:
        """
        Run the analysis
        """
        # Init
        frames = []
        timeblockcounter = 0
        initiation = True

        # Parameters for lucas kanade optical flow
        lk_params = dict(winSize=(100, 100), maxLevel=2, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 0.003))

        # Results (timesteps, x, lines)
        results = np.zeros((self.timesteps_in_timeblock, (len(self.ref_points) - 1) * self.grid_points_length + 1, self.grid_points_width))

        # Loop through the mp4s
        for current_mp4 in self.mp4_files:

            # Obtain settings
            cap = cv2.VideoCapture(str(self.video.path / current_mp4))
            self.frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = cap.get(cv2.CAP_PROP_FPS) * self.video.slow_down
            self.dt = 1 / self.fps

            # Print info
            print(f"Start assessing: {current_mp4}")
            print(f"Resolution: {self.frame_width}x{self.frame_height}")
            print(f"FPS: {round(self.fps, 3)} per sec")
            print(f"Timestep: {round(self.dt, 3)} sec")
            print(f"Wavefront movement in video: {self.video.direction.name}")
            
            # Create an _initial.png frame
            if not os.path.exists(self.video.path / str(current_mp4.split(".")[0] + "_initial.png")):
                self.create_initial_image(self.video.path / str(current_mp4.split(".")[0] + "_initial.png"))

            # When initiating, create a new folder and video, set to correct frame
            if initiation:
                self.__init_new_timeblock()
                cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame - 1)
                initiation = False

            # Loop through every frame
            while True:

                # Print info
                if timeblockcounter % 100 == 0:
                    now = datetime.now()
                    print(f"[{now.strftime('%H:%M:%S')}] Timeblock: {self.current_timeblock} Frame: {timeblockcounter}")

                # Read frame
                ret, frame = cap.read()

                # If the frame is not read succesfully, we are done with the video file!
                if not ret:
                    break

                # Obtain the gray frame
                frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Filter for white
                frame_diff = frame
                frame_diff = cv2.cvtColor(frame_diff, cv2.COLOR_BGR2GRAY)
                frame_diff = cv2.subtract(frame_diff, self.graybuffer[0])
                frame_diff = cv2.morphologyEx(frame_diff, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

                # Convert the frame to HSV color space
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

                # Split the HSV image into channels
                h, s, v = cv2.split(hsv)

                # Reduce the brightness of the V channel by 50%
                v_half = np.clip(v * 0.5, 0, 255).astype(np.uint8)

                # Merge the modified channels back together
                hsv_half = cv2.merge([h, s, v_half])

                # Convert the modified HSV image back to BGR color space
                frame = cv2.cvtColor(hsv_half, cv2.COLOR_HSV2BGR)
                frame = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)


                ########################################################################################################
                # CALCULATE DRONE MOVING VECTOR
                ########################################################################################################

                if self.track:
                    # Track the region outside the experimental setup
                    self.p_1, st_1, _ = cv2.calcOpticalFlowPyrLK(self.graybuffer[-1], frame_gray, self.p_0, None, **lk_params)

                    # Total dx/dy
                    dx = []
                    dy = []

                    # New points
                    good_new = self.p_1[st_1 == 1]
                    good_old = self.p_0[st_1 == 1]
                    for _, (new, old) in enumerate(zip(good_new, good_old)):
                        a, b = new.ravel()
                        frame = cv2.circle(frame, (int(a), int(b)), 2, (0, 255, 0), -1)
                        dx.append(new[0] - old[0])
                        dy.append(new[1] - old[1])

                    # Correct
                    self.ref_points[:, :, 0] += trim_mean(dx, self.moving_objects_trim)
                    self.ref_points[:, :, 1] += trim_mean(dy, self.moving_objects_trim)


                ########################################################################################################
                # CALCULATE GRID
                ########################################################################################################

                # Grid init
                grid = np.zeros(((len(self.ref_points) - 1) * self.grid_points_length + 1, self.grid_points_width, 2))

                # Calculate the grid between reference points
                for refid in range(len(self.ref_points)):

                    gridid = refid * self.grid_points_length

                    # Calculate the verticals between the reference points
                    if self.video.direction in [Direction.LEFT_TO_RIGHT, Direction.RIGHT_TO_LEFT]:

                        # Horizontal footage
                        x1, y1 = self.ref_points[refid][np.argmin(self.ref_points[refid][:, 1])]
                        x2, y2 = self.ref_points[refid][np.argmax(self.ref_points[refid][:, 1])]

                        diff_y = (y2 - y1) / (self.grid_points_width + 1)
                        diff_x = (x2 - x1) / (self.grid_points_width + 1)

                        grid[gridid, :] = np.array([
                            x1 + np.arange(1, self.grid_points_width + 1) * diff_x, 
                            y1 + np.arange(1, self.grid_points_width + 1) * diff_y]).T

                    else:
                        # Vertical footage
                        raise NotImplementedError()

                    # Calculate the horizontals between the earlier defined grid points
                    if refid != 0:

                        # For each two pair of points
                        for j in range(self.grid_points_width):
                            start = gridid - self.grid_points_length
                            end = gridid
                            x1, y1 = grid[start, j]
                            x2, y2 = grid[end, j]

                            diff_x = (x2 - x1) / (self.grid_points_length)
                            diff_y = (y2 - y1) / (self.grid_points_length)

                            grid[(start+1):end, j] = np.array(
                                [x1 + np.arange(1, self.grid_points_length) * diff_x,
                                 y1 + np.arange(1, self.grid_points_length) * diff_y]).T

                # Collect gray
                for col in range(len(grid)):
                    for row in range(len(grid[0])):
                        point_x, point_y = int(grid[col, row, 0]), int(grid[col, row, 1])
                        if point_x < self.frame_width and point_x >= 0 and point_y < self.frame_height and point_y > 0:
                            results[timeblockcounter, col, row] = frame_diff[int(point_y), int(point_x)] / 255
                        else:
                            results[timeblockcounter, col, row] = -1
                            print("[WARNING] Point outside frame, neglected.")

                # Draw refrence points
                for pair in self.ref_points:
                    ref1 = (int(pair[0][0]), int(pair[0][1]))
                    ref2 = (int(pair[1][0]), int(pair[1][1]))
                    frame = cv2.circle(frame, ref1, 2, (0, 0, 255), -1)
                    frame = cv2.circle(frame, ref2, 2, (0, 0, 255), -1)
                    frame = cv2.line(frame, ref1, ref2, (0, 0, 255), 1)

                # Draw grid
                for point in grid.reshape((len(grid) * len(grid[1]), 2)):
                    point = (int(point[0]), int(point[1]))
                    frame = cv2.circle(frame, point, 1, (0, 0, 255), -1)

                # Indicate overtopping flow
                frame_diff_3canal = cv2.cvtColor(frame_diff, cv2.COLOR_GRAY2RGB)
                frame_diff_3canal[:, :, 1:] = 0
                frame_diff_3canal[:, :, 0]
                frame_diff_3canal[:, :, 0][frame_diff_3canal[:, :, 0] <= 50] = 0
                frame_diff_3canal[:, :, 0][frame_diff_3canal[:, :, 0] > 50] = 255
                blended_frame = cv2.addWeighted(frame, 1.0, frame_diff_3canal, 1.0, 0)


                ########################################################################################################
                # SAVING AND FINISHING
                ########################################################################################################

                # Update buffer
                for n in range(self.image_buffer - 1):
                    self.graybuffer[n] = self.graybuffer[n + 1].copy()
                self.graybuffer[self.image_buffer - 1] = frame_gray

                # Updating Previous frame and points
                if self.track:
                    self.p_0 = good_new.reshape(-1, 1, 2)

                # Save frame
                self.writer.write(blended_frame)

                # Add 1 to nframe
                frames.append([current_mp4, cap.get(cv2.CAP_PROP_FPS), self.video.slow_down])

                # Time block counter check
                timeblockcounter += 1
                if timeblockcounter == self.timesteps_in_timeblock:

                    # Save
                    self.__save_results(results, frames)

                    # Reset
                    timeblockcounter = 0
                    frames = []
                    results[:] = 0

                    # New 
                    self.current_timeblock += 1
                    self.__init_new_timeblock()

        # End
        cv2.destroyAllWindows()
        cap.release()

        # Save results
        self.__save_results(results[:timeblockcounter], frames)


    def __save_results(self, results, frames):
        # Print info
        print("Saving...")

        # Path
        results_path = self.video.path / self.output_folder
        current_folder = f"timeblock_{str(self.current_timeblock).zfill(5)}"

        # Save video
        self.writer.release()

        # Save buffer
        if not os.path.exists(results_path / current_folder / "buffer"):
            os.makedirs(results_path / current_folder / "buffer")
        for _nbuffer, _bufferim in enumerate(self.graybuffer):
            cv2.imwrite(str(results_path / current_folder / "buffer" / f"buffer{_nbuffer}.png"), _bufferim)
        
        # Save ref_points
        pd.DataFrame(self.ref_points.reshape((len(self.ref_points), 4)), columns=["X0", "Y0", "X1", "Y1"]).to_excel(str(results_path / current_folder / "reference_points.xlsx"))
        
        # Create a reference points png
        self.create_initial_image(str(results_path / current_folder / "reference_points.png"))

        # Save tracking points
        if self.track:
            pd.DataFrame(self.p_0.reshape((len(self.p_0), 2)), columns=["X", "Y"]).to_excel(str(results_path / current_folder / "tracking_points.xlsx"))

        # Save framecounter
        pd.DataFrame(frames, columns=["mp4_file", "fps", "slowdown"]).to_excel(str(results_path / current_folder / "frames.xlsx"))

        # Save results
        if not os.path.exists(results_path / current_folder / "raw"):
            os.makedirs(results_path / current_folder / "raw")
        start = self.current_timeblock * self.timesteps_in_timeblock * self.dt
        for npoint in range(self.grid_points_width):
            df = pd.DataFrame(results[:, :, npoint])
            df.index = start + np.arange(0, (results.shape[0]) * self.dt, self.dt)
            df.columns = np.arange(0, (results.shape[1] - 1) / self.grid_points_length + 0.0001, 1 / self.grid_points_length)
            df.to_csv(results_path / current_folder / "raw" / f"line{npoint}.csv")
        
        # Print done
        print("...done!")
    

    def create_initial_image(self, path):
        # Create an empty frame
        init_frame = np.zeros((self.frame_height, self.frame_width, 3))

        # Create a grid with reference points
        for (p0, p1) in self.ref_points:

            # Convert to int
            p0_x = int(p0[0])
            p0_y = int(p0[1])
            p1_x = int(p1[0])
            p1_y = int(p1[1])

            # Check if the point is within the grid
            fail = False
            for p_x in [p0_x, p1_x]:
                if p_x < 0 or p_x >= self.frame_width:
                    print(f"[WARNING] Skipped point outside frame during creation of reference frame! (x = {p_x})")
                    fail = True
            for p_y in [p0_y, p1_y]:
                if p_y < 0 or p_y >= self.frame_height:
                    print(f"[WARNING] Skipped point outside frame during creation of reference frame! (y = {p_y})")
                    fail = True

            # If they are not outside the frame, add the red pixels
            if not fail:
                init_frame[p0_y, p0_x] = [0, 0, 255]
                init_frame[p1_y, p1_x] = [0, 0, 255]

        # Place pixels
        if self.video.direction == Direction.LEFT_TO_RIGHT:
            left = [0, 255, 0]
            right = [255, 0, 0]
        else:
            left = [255, 0, 0]
            right = [0, 255, 0]

        # Left
        if np.max(init_frame[int(self.frame_height / 2), 0]) == 0:
            init_frame[int(self.frame_height / 2), 0] = left
        else:
            init_frame[int(self.frame_height / 2) - 1, 0] = left

        # Right
        if np.max(init_frame[int(self.frame_height / 2), self.frame_width - 1]) == 0:
            init_frame[int(self.frame_height / 2), int(self.frame_width - 1)] = right
        else:
            init_frame[int(self.frame_height / 2) - 1, int(self.frame_width - 1)] = right

        # Save frame
        cv2.imwrite(str(path), init_frame)


    def __init_new_timeblock(self):
        # Path
        results_path = self.video.path / self.output_folder
        new_folder = f"timeblock_{str(self.current_timeblock).zfill(5)}"

        # Create a new folder
        if not Path(results_path / new_folder).exists():
            os.makedirs(results_path / new_folder)
        
        # New video
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(str(results_path / new_folder / f"video_output.mp4"), fourcc, self.fps, (self.frame_width, self.frame_height))
