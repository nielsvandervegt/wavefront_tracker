# Wavefront Tracker

The Python package Wavefront Tracker provides a video analysis tool for tracking foaming fronts of overtopping waves and bores. The package is a proof of concept and may therefore contain bugs and unoptimized workflows. It can detect the wave front at specified interval points along one or multiple cross-sections. This produces a time series of grayscale values at each detection point, where values close to 1 indicate a higher likelihood of belonging to the wave front. Further analysis, such as analyzing and combining these time series to derive front velocities, is not yet implemented in the Python package.

This Python package is developed as part of the Ph.D. project of Niels van der Vegt and part of the publication 'Spatiotemporal levee erosion and wavefront velocity dataset from in-situ wave overtopping experiments' by Ebrahimi et al. (in press). The package is published under the GNU GPL-3 license.

For questions regarding the use of this package, contact `n.vandervegt@utwente.nl` / `n.vandervegt@hkv.nl`.

## Getting started

The folder `wavefront_tracker` is a Python package. For more detailed documentation, refer to the inline comments within the package.

The `example.py` script provides an overview of the current workflow.

The `example_files` directory contains example input and output. Due to file size limitations, not all input and output files are included. The video file is the property of Infram-Hydren and is therefore not included.

`example.py`:
```py
import wavefront_tracker as wft

from pathlib import Path

# The wavefront tracker is a proof of concept and has not been further developed.
# Please note, the work flow is not optimized at all.

# Experimental series, recorded as a continuous sequence across multiple video files
path = Path("C:/path/to/mp4/excel/and/png/files")
mp4 = ["GX010915_video.MP4", "GX020915_video.MP4"]


# We need an initial frame, where:
# 1) The dimensions of the .png is equal to the dimensions of the mp4
# 2) The background is transparant
# 3) The meter marks are indicated by a red pixel on both sides (#FF0000)
# 4) The top of the slope is indicated by a single green pixel (#00FF00) to the left of the first measurement point (x_pixel < x_measurement_point1)
# 5) The bottom of the slope is indicated by a single blue pixel (#0000FF) to the right of the last measurement point (x_pixel > x_measurement_pointn)
ref_points = "GX010915_initial.png"

# To make it easier, the wavefront tracker has a function to convert the first frame of a mp4 to a .png
# wft.CommonTools.generate_starting_frame(path / mp4[0])


# Next, we need to define at which second in the mp4 the overtopping event happens.
# It is important to determine the time (in seconds) at which the overtopping event has not yet reached the first meter mark.
# Future work could try to automate this
volume_time = "volume_time.xlsx"


# Now we can define a video object
video = wft.Video(path, mp4, ref_points, volume_time)


# To check if the time of each overtopping event is correctly defined, one can use the function below.
# This function exports .png of the first frame of each overtopping event.
# These frames can be used to check if the overtopping event is just before the first meter mark.
# wft.CommonTools.generate_control_figues(video)

# Start the analysis, see documentation in the code for settings
analysis = wft.Analyse(video, timesteps_in_timeblock=1000, track=False)
analysis.image_buffer = 30  # Buffer size
analysis.start(force_restart=True)

# Postprocessing
post = wft.PostProcess(video)
post.combine_raw_output()
post.count_frames()
post.combine_video()
# post.remove_old_videos()  # Be careful with this function as Python will automatically try to delete the unused video files

# The wavefront tracker returns for each cross-section a seperate file (line{nr}.csv)
# Within this file, for each point along this cross-section, a time series of the front detection is exported
# Scripts like peak detecting can then be used to detect the arrival time of the wavefront and use it to determine the front velocity.
# These steps are not (yet) included in the wavefront tracker package
```

## Acknowledgements
This work is part of the Perspectief research programme Future Flood Risk Management Technologies for Rivers and Coasts with project number P21-23. This programme is financed by Domain Applied and Engineering Sciences of the Dutch Research Council (NWO).
