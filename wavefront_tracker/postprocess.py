import numpy as np
import os
import pandas as pd

from moviepy.editor import VideoFileClip, concatenate_videoclips

from .video import Video


class PostProcess:

    def __init__(self, video: Video, folder: str = "raw_output"):
        self.video = video
        self.folder = folder
        self.timeblocks = np.sort([f for f in os.listdir(self.video.path / folder) if f.lower().startswith("timeblock_")])
        self.nlines = len(os.listdir(self.video.path / self.folder / self.timeblocks[0] / "raw"))

    
    def combine_raw_output(self):
        # Print start
        print("[INFO] Start combining output...")

        # Create new folder
        if not os.path.exists(self.video.path / "output"):
            os.makedirs(self.video.path / "output")

        # Per line
        for nline in range(self.nlines):

            # Print
            print(f"...Line: {nline}...")

            # Results
            data = None

            # Per timeblock
            for tb in self.timeblocks:

                # Read
                df = pd.read_csv(self.video.path / self.folder / tb / "raw" / f"line{nline}.csv")
                _data = df.to_numpy()

                # Concat
                if data is None:
                    data = _data
                else:
                    data = np.concatenate((data, _data), axis=0)
        
            # Save
            df = pd.DataFrame(data, columns=df.columns)
            df.set_index(df.columns[0], inplace=True)
            df.to_csv(self.video.path / "output" / f"line{nline}.csv")
        
        # Print done
        print("...done!")


    def count_frames(self):
        # Print data
        print("[INFO] Count frames...")

        # Results
        results = {}

        # Per timeblock
        for tb in self.timeblocks:

            # Load file
            df = pd.read_excel(self.video.path / self.folder / tb / "frames.xlsx")

            # Per mp4 file
            for file, df in df.groupby(by = ["mp4_file"]):

                # Create
                if not file[0] in results:
                    results[file[0]] = {}
                    results[file[0]]["frames"] = 0
                    results[file[0]]["fps"] = float(df.iloc[0]["fps"])
                    results[file[0]]["slowdown"] = float(df.iloc[0]["slowdown"])
                
                # Increase frames
                results[file[0]]["frames"] = results[file[0]]["frames"] + len(df)
        
        # Save
        data = []
        for key in results.keys():
            data.append([key, results[key]["frames"], results[key]["fps"], results[key]["slowdown"]])
        
        # Save
        pd.DataFrame(data, columns=["mp4_file", "frames", "fps", "slowdown"]).to_excel(self.video.path / "frame_count.xlsx")
        
        # Print done
        print("...done!")


    def combine_video(self, remove_old_videos: bool = False):
        # Print data
        print("[INFO] Combining videos into one...")

        # Collect all mp4s
        mp4_paths = [str(self.video.path / self.folder / tb / "video_output.mp4") for tb in self.timeblocks]

        # Load the video clips
        clips = [VideoFileClip(file) for file in mp4_paths]

        # Concatenate the video clips
        final_clip = concatenate_videoclips(clips)

        # Write the final video to a file
        final_clip.write_videofile(os.path.join(self.video.path, "result.mp4"))
        
        # Print done
        print("...done!")

        # Delete old videos
        if remove_old_videos:
            self.remove_old_videos()


    def remove_old_videos(self):
        # Print data
        print("[INFO] Removing old videos...")

        # Collect all mp4s
        mp4_paths = [self.video.path / self.folder / tb / "video_output.mp4" for tb in self.timeblocks]

        # Delete
        for mp4_path in mp4_paths:
            os.remove(mp4_path)
        
        # Print done
        print("...done!")
