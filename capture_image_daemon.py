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
import socket
import signal
import select

gi.require_version("Tcam", "0.1")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")

from gi.repository import Tcam, Gst, GstVideo

framecount = 0
ready = False
sav_prefix = ''
done = False

def sigHandler(signum, frame):
    global done
    done = True
    return


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

            if stride == 1:
                dtype = np.uint8
            elif stride == 2:
                dtype = np.uint16
            elif stride == 4:
                dtype = np.uint32

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
            imgdata = np.asarray(np.reshape(imgdata, (video_info.height, video_info.width)), dtype = dtype)

            global framecount, ready, sav_prefix

            if (ready):
                savfname = '{}_{}_{}.npy'.format(sav_prefix, int(timestamp * 1e9) // 1000, framecount)
                np.save(savfname, imgdata)
                framecount += 1
                ready = False
                # print('In Callback:', ready)

                # output_str = "Captured frame {}, Pixel Value={} Timestamp={}".format(framecount,
                #                                                                    pixel_data,
                #                                                                    timestamp)

                # print(output_str, end="\r")  # print with \r to rewrite line

        finally:
            gst_buffer.unmap(buffer_map)

    return Gst.FlowReturn.OK


def main():
    signal.signal(signal.SIGINT, sigHandler)
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

    # tell appsink what function to call when it notifies us
    sink.connect("new-sample", callback, sys.argv[0])

    pipeline.set_state(Gst.State.PLAYING)
    
    global framecount, ready, sav_prefix, done

    trigger_mode_type = source.get_tcam_property_type("Trigger Mode")

    source.set_tcam_property("Exposure Max", 60000) # 60 us max exposure
    # set up socket connection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 65432))
        sock.listen()
        sock.settimeout(1)
        init_conn_fails = 0
        while not done: # deals with Ctrl + C
            try:
                conn, addr = sock.accept() # accept a connection
            except socket.timeout:
                init_conn_fails += 1
                if init_conn_fails > 5:
                    # reset sink props
                    if trigger_mode_type == "enum":
                        source.set_tcam_property("Trigger Mode", "Off")
                    else:
                        source.set_tcam_property("Trigger Mode", False)
                    source.set_tcam_property("Gain Auto", True) # no auto gain
                    source.set_tcam_property("Exposure Auto", True)
                continue

            init_conn_fails = 0
            size = conn.recv(4, socket.MSG_WAITALL) # receive first 8 bytes of the message
            try:
                size = int(size)
            except Exception:
                print('%s is not acceptable size. Closing connection.'%(size))
                conn.sendall('ERROR'.encode('utf-8'))
                conn.close()
                continue
            print('Receiving %d bytes...'%(size))
            msg = conn.recv(size, socket.MSG_WAITALL).decode('utf-8')
            print('Received command: %s'%(msg))
            msg = msg.lstrip(' ')
            words = msg.split(' ')
            if (len(words) != 4):
                print('Received %d command words. Error.')
                conn.sendall('ERROR'.encode('utf-8'))
                conn.close()
                continue
            sav_prefix = words[0]
            print('Save prefix: %s'%(sav_prefix))
            try:
                exposure = int(words[1])
            except Exception:
                print('%s not valid exposure.'%(words[1]))
                conn.sendall('ERROR'.encode('utf-8'))
                conn.close()
                continue
            print('Exposure: %d us'%(exposure))
            try:
                count = int(words[2])
            except Exception:
                print('%s not valid counts.'%(words[2]))
                conn.sendall('ERROR'.encode('utf-8'))
                conn.close()
                continue
            try:
                gain = int(words[3])
            except Exception:
                print('%s not valid gain.'%(words[3]))
                gain = 10
                
            print('Frames: %d'%(count))
            # at this point we have all valid data

            # Set source props
            source.set_tcam_property("Gain Auto", True) # no auto gain
            # source.set_tcam_property("Gain", gain) # max
            source.set_tcam_property("Exposure Auto", True)
            # print(source.get_tcam_property('Gain'))
            # source.set_tcam_property("Exposure Time (us)", exposure) # 100000 us exposure, should be user input
            # print(source.get_tcam_property('Exposure Time (us)'))
            # set exposure mode to trigger
            if trigger_mode_type == "enum":
                source.set_tcam_property("Trigger Mode", "On")
            else:
                source.set_tcam_property("Trigger Mode", True)

            exposure *= 1e-6
            time_sleep = 1
            time_sleep = 1.1 * exposure if exposure * 0.9 > time_sleep else time_sleep # 1 second per frame if exposure < 0.9 s, else 1.1 * exposure
            # start taking exposures
            time.sleep(2) # wait for triggering to stop
            framecount = 0
            while framecount < count and not done:
                ready = True
                ret = source.set_tcam_property("Software Trigger", True) # trigger picture
                if not ret:
                    print("!!! Could not trigger. !!!\n")
                    break
                time.sleep(time_sleep) # wait
                # while ready and not done:
                #     print('In trigger:', ready)
                #     time.sleep(0.01)
                print('Frames acquired: %d'%(framecount), end = '\r')
            print('\n')
            ready = False # stop saving images
            # set trigger mode to auto

            conn.sendall('DONE!'.encode('utf-8')) # indicate done
            conn.close()

        sock.close()
    # sink.set_property("emit-signals", False) # disable sink

    if trigger_mode_type == "enum":
        source.set_tcam_property("Trigger Mode", "Off")
    else:
        source.set_tcam_property("Trigger Mode", False)
            
    source.set_tcam_property("Gain Auto", True) # no auto gain
    source.set_tcam_property("Exposure Auto", True)
    # deactivate trigger mode
    # this is simply to prevent confusion when the camera ist started without wanting to trigger
    time.sleep(1)
    pipeline.set_state(Gst.State.NULL) # stop pipeline
    time.sleep(1)


if __name__ == "__main__":
    main()
