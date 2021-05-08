import cv2
import base64
import datetime

import numpy as np

class Chip:
    def __init__(self, video_source):
        self.source = video_source
        self.way = ''
        self.length = ''
        self.keyfeature = ''
        self.chipname = ''

def get_audio(video_path: str, audio_path: str) -> None:
    """
    Get audio from video file and store to audio path.
    :param video_path: video file path.
    :param audio_path: audio file path.
    :return: None.
    """
    pass

def encode(to_content: str) -> str:
    assert not isinstance(to_content, str), "[ERROR]:Argument of 'to_content' must be a string"
    return str(base64.b64encode(to_content.encode('utf-8')), 'utf-8')

def mktime_form(time_: int, fps: int) -> str:
    #hours = _second//3600
    #minutes = (_second % 3600)//60
    """
    hours = int(_second)//3600
    minutes = (int(_second) % 3600)//60
    seconds = ((_second % 3600) % 60)
    return str(hours) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)
    """
    return str(datetime.timedelta(seconds=time_ / float(fps)))

def mktime_sec(_second):
    #hours = _second//3600
    #minutes = (_second % 3600)//60
    hours = int(_second)//3600
    minutes = (int(_second) % 3600)//60
    seconds = ((_second % 3600) % 60)
    return str(hours) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)

