import cv2
import os
import pandas as pd

from pathlib import Path
from typing import TYPE_CHECKING

# Prevent circular import, use Video only for typing
if TYPE_CHECKING:
    from .video import Video


class CommonTools:
    """
    A class with common tools used within the package
    """

    @staticmethod
    def generate_starting_frame(mp4_path: str | Path):
        """
        Generate a PNG of the starting frame of the Video object

        Parameters
        ----------
        mp4_path : str | Path
            Path to mp4 file
        """
        # Convert to Path
        if not isinstance(mp4_path, Path):
            mp4_path = Path(mp4_path)

        # Open videofile
        cap = cv2.VideoCapture(str(mp4_path))

        # Set frame postion
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        # Read the frame
        ret, frame = cap.read()

        # Check if the frame is read successfully
        if not ret:
            print("Error: Unable to read frame.")
            exit()

        # Export the frame as an image
        cv2.imwrite(str(mp4_path.parent / (mp4_path.name.split(".")[0] + ".png")), frame)

        # Release the videofile
        cap.release()

    @staticmethod
    def generate_control_figues(video: 'Video', dt: float = 0):
        """
        Generate control figures for each released volume in a folder 'control figures'

        Parameters
        ----------
        video: Video
            The Video object to create the control volumes for
        dt: float
            Difference between frame 1 and 2 for each overtopping (default = 0)
        """        
        # Loop through each mp4 file
        for mp4, df in video.volume_time.groupby(by = ["mp4_file"]):

            # Select the MP4 file
            path_mp4 = [_mp4 for _mp4 in video.mp4 if mp4[0].lower() in str(_mp4).lower()]
            if len(path_mp4) != 1:
                raise ValueError(f"[ERROR] Found {len(path_mp4)} files, need 1.")

            # Load video file
            cap = cv2.VideoCapture(str(video.path / path_mp4[0]))
                
            # Check output folder
            if not os.path.exists(video.path / "control_figures"):
                os.makedirs(video.path / "control_figures")

            # Per volume
            for event, row in df.iterrows():
                
                # Event and framenumber
                fps = cap.get(cv2.CAP_PROP_FPS)
                    
                # Print
                print(f"Event {event}")

                # Frame array
                frames = [int(row['seconds'] * fps)] if dt == 0 else [int(row['seconds'] * fps), int((row['seconds'] + dt * video.slow_down) * fps)]
                for frameid, frame_number in enumerate(frames):

                    # Set frame postion
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

                    # Read the frame
                    ret, frame = cap.read()

                    # Check if the frame is read successfully
                    if not ret:
                        print(f"Error: Unable to read frame {frame_number}.")
                        exit()
                    
                    # Filename
                    if len(frames) == 1:
                        filename = f'event_{event}.jpg'
                    else:
                        filename = f'event_{event}_{frameid+1}.jpg'

                    # Export the frame as an image
                    cv2.imwrite(str(video.path / "control_figures" / filename), frame)

            # Release the videofile
            cap.release()

    @staticmethod
    def count_frames(video: 'Video'):
        """
        Count the number of frames in each mp4 file and store it in 'frame_count.xlsx'

        Parameters
        ----------
        video: Video
            The Video object for which the frames have to be counted
        """
        # Init variables
        data = []

        # Loop through each mp4 file
        for mp4, _ in video.volume_time.groupby(by = ["mp4_file"]):

            # Select the MP4 file
            path_mp4 = [_mp4 for _mp4 in video.mp4 if mp4[0].lower() in str(_mp4).lower()]
            if len(path_mp4) != 1:
                raise ValueError(f"[ERROR] Found {len(path_mp4)} files, need 1.")

            # Load video file
            print(f"Counting frames for {mp4[0]}...")
            cap = cv2.VideoCapture(str(path_mp4[0]))

            # Count
            frames = 0
            while True:
                status, _ = cap.read()
                if not status:
                    break
                frames += 1
                if frames % 1000 == 0:
                    print(f"...{frames}...")
            
            # Collect data
            data.append([mp4[0], frames, cap.get(cv2.CAP_PROP_FPS), video.slow_down])
            print(f"...found {frames} frames.")

            # Release the videofile
            cap.release()
        
        # Store in Excel
        pd.DataFrame(data, columns=["mp4_file", "frames", "fps", "slowdown"]).to_excel(str(path_mp4[0].parent / "frame_count.xlsx"))
