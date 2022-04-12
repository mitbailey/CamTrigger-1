#!/usr/bin/env python3

# Copyright 2017 The Imaging Source Europe GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# This example will show you how to enable trigger-mode
# and how to trigger images with via software trigger.
#


import sys
import gi
import time
import datetime as dt
import numpy as np
import matplotlib.pyplot as plt

gi.require_version("Tcam", "0.1")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")

from gi.repository import Tcam, Gst, GstVideo

framecount = 0
ready = False


def callback(appsink, user_data):
    """
    This function will be called in a separate thread when our appsink
    says there is data for us. user_data has to be defined
    when calling g_signal_connect. It can be used to pass objects etc.
    from your other function to the callback.
    """
    sample = appsink.emit("pull-sample")

    if sample:

        caps = sample.get_caps()

        gst_buffer = sample.get_buffer()

        try:
            (ret, buffer_map) = gst_buffer.map(Gst.MapFlags.READ)

            video_info = GstVideo.VideoInfo()
            video_info.from_caps(caps)

            stride = video_info.finfo.bits / 8

            pixel_offset = int(video_info.width / 2 * stride +
                               video_info.width * video_info.height / 2 * stride)

            # this is only one pixel
            # when dealing with formats like BGRx
            # pixel_data will have to consist out of
            # pixel_offset   => B
            # pixel_offset+1 => G
            # pixel_offset+2 => R
            # pixel_offset+3 => x
            pixel_data = buffer_map.data[pixel_offset]
            timestamp = dt.datetime.now().timestamp()
            imgdata = buffer_map.data # .copy()
            imgdata = np.asarray(np.reshape(imgdata, (480, 640)), dtype = np.uint8)

            global framecount, ready

            if (ready):
                savfname = '{}_{}_{}.npy'.format(user_data, framecount, int(timestamp * 1e9) // 1000)
                np.save(savfname, imgdata)
                framecount += 1

            output_str = "Captured frame {}, Pixel Value={} Timestamp={}".format(framecount,
                                                                                 pixel_data,
                                                                                 timestamp)

            # print(output_str, end="\r")  # print with \r to rewrite line

        finally:
            gst_buffer.unmap(buffer_map)

    return Gst.FlowReturn.OK


def main():
    if len(sys.argv) == 3 or len(sys.argv) == 4:
        pass
    else:
        return

    try:
        count = int(sys.argv[3])
    except Exception:
        count = 10
    
    try:
        exposure = int(sys.argv[2])
    except Exception:
        exposure = 100000

    Gst.init([sys.argv[0]])  # init gstreamer

    # this line sets the gstreamer default logging level
    # it can be removed in normal applications
    # gstreamer logging can contain verry useful information
    # when debugging your application
    # see https://gstreamer.freedesktop.org/documentation/tutorials/basic/debugging-tools.html
    # for further details
    Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)

    serial = None

    pipeline = Gst.parse_launch("tcambin name=source"
                                " ! tee name=t"
                                " t. ! queue ! videoconvert ! ximagesink"
                                " t. ! queue ! videoconvert"
                                " ! appsink name=sink")

    # test for error
    if not pipeline:
        print("Could not create pipeline.")
        return

    # The user has not given a serial, so we prompt for one
    source = pipeline.get_by_name("source")
    if serial is not None:
        source.set_property("serial", serial)

    sink = pipeline.get_by_name("sink")

    # tell appsink to notify us when it receives an image
    sink.set_property("emit-signals", True)

    user_data = np.zeros((480, 640), dtype = float)

    # tell appsink what function to call when it notifies us
    sink.connect("new-sample", callback, sys.argv[1])

    pipeline.set_state(Gst.State.PLAYING)
    time.sleep(2)

    # print("Press Ctrl-C to stop.")

    source.set_tcam_property("Gain Auto", False) # no auto gain
    source.set_tcam_property("Gain", 10) # max
    source.set_tcam_property("Exposure Auto", False)
    # print(source.get_tcam_property('Gain'))
    source.set_tcam_property("Exposure Time (us)", exposure) # 100000 us exposure, should be user input
    # print(source.get_tcam_property('Exposure Time (us)'))

    trigger_mode_type = source.get_tcam_property_type("Trigger Mode")

    if trigger_mode_type == "enum":
        source.set_tcam_property("Trigger Mode", "On")
    else:
        source.set_tcam_property("Trigger Mode", True)
    global ready
    time.sleep(1)
    exposure *= 1e-6
    time_sleep = 0.5
    time_sleep = 1.1 * exposure if exposure * 0.9 > time_sleep else time_sleep # 1 second per frame if exposure < 0.9 s, else 1.1 * exposure
    while framecount < count:
        ready = True
        ret = source.set_tcam_property("Software Trigger", True)

        # if ret:
            # print("=== Triggered image. ===\n")
            
        # else:
        if not ret:
            print("!!! Could not trigger. !!!\n")
        # print(source.get_tcam_property("Software Trigger"))
        time.sleep(time_sleep) # image every second
    # deactivate callback
    ready = False
    sink.set_property("emit-signals", False)
    # deactivate trigger mode
    # this is simply to prevent confusion when the camera ist started without wanting to trigger
    if trigger_mode_type == "enum":
        source.set_tcam_property("Trigger Mode", "Off")
    else:
        source.set_tcam_property("Trigger Mode", False)
    time.sleep(1)
    pipeline.set_state(Gst.State.NULL)
    time.sleep(1)


if __name__ == "__main__":
    main()
