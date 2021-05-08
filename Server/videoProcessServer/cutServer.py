import os
import cv2
import json
import time
import signal
import shutil
import pymysql
import datetime
import traceback
import subprocess

import tornado.web
import tornado.ioloop
import tornado.httpserver

import numpy as np
import multiprocessing as mp

from easydict import EasyDict as edict
from tornado.platform.asyncio import AsyncIOMainLoop

from tools.log import write_log
from Server.recognizationServer.addFeature import AddHandler
from Server.recognizationServer.face import FaceDetecter
from Server.recognizationServer.baidu_speech import BaiduSRC
from Server.videoProcessServer.fetchStream import FetchStream

from ..handler import WebHandler
from .cutHandler import CutHandler
from .utils import mktime_form, mktime_sec
from .mysqlTools import SQLHold

LOG_DIR = os.path.join('log', 'cutServer')
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)

def wait_to_create(file_name: str, process_name: str, pr_id: str) -> None:
    while not os.path.exists(file_name) or os.path.getsize(file_name) == 0:
        time.sleep(1)
        message = "[INFO]: {} This process: {} is loading ... ...".format(str(datetime.datetime.now()).split('.')[0], process_name)
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + pr_id + '.log'))

def get_feature(mysql: SQLHold, pr_id: str) -> dict:
    message = "[INFO]: {} Get feature.".format(str(datetime.datetime.now()).split('.')[0])
    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + pr_id + '.log'))
    command = 'select * from face_feature'
    mysql.execute_command(command)
    result = mysql.fetchall()
    feature_dict = {}
    for i, name, item in result:
        item = np.asarray([float(val) for val in item.split(',')], dtype=np.float32)
        feature_dict.update({name: item})
    message = "[INFO]: {} there are {} face feature".format(str(datetime.datetime.now()).split('.')[0], len(feature_dict))
    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + pr_id + '.log'))

    return feature_dict


def get_face_data(face_feature_dict: dict, key_words: list):
    key_name = []
    face_feature = []
    for item in key_words:
        key_name.append(item)
        face_feature.append(face_feature_dict[item])

    return key_name, face_feature

get_static_time = lambda ad_frame, ad_all_frame, vd_all_frame, fps: (ad_frame / ad_all_frame) * (vd_all_frame / fps)

class CutServer(mp.Process):

    def __init__(self, data: dict):
        super(CutServer, self).__init__()
        self.data = data
        self.__sended = []
        self.__send_count = 0
        self.key_words = []
        self.cap = None
        self.mysql = None
        self.mode = data['video_mode']
        self.video_name = data['video_name'].split('.')[0] if 'local' == self.mode else \
            data['video_address'].split('/')[-1].split('.')[0]  # 仅记录video的名称（不含路径和后缀名）
        self.initialize()
        ip_dir = os.path.join(self.output_root_dir, data['ip'])
        if not os.path.exists(ip_dir):
            os.mkdir(ip_dir)
        self.output_dir = os.path.join(ip_dir, self.video_name)
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        else:
            shutil.rmtree(self.output_dir)
            message = "[INFO]: {} remove dir: {}.".format(str(datetime.datetime.now()).split('.')[0], self.output_dir)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: remove dir:", self.output_dir)
            os.mkdir(self.output_dir)
            message = "[INFO]: {} New dir: {}.".format(str(datetime.datetime.now()).split('.')[0], self.output_dir)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: New dir:", self.output_dir)
        # 视频路径或者url
        self.video_path = os.path.join(self.video_root_path, data['video_name']) if \
            data['video_mode'] == 'local' else data['video_address']

        self.speech_detector = None
        if self.__sr_on == 'on':
            self.__ad_main, self.__ad_proc = mp.Pipe(duplex=True)
            self.speech_detector = BaiduSRC(api_key=self.api_key,
                                            secret_key=self.secret_key,
                                            dev_pid=self.dev_pid,
                                            pipe=self.__ad_proc)
            self.speech_detector.start()

        self.start_time = time.time()
        self._main, self._proc = mp.Pipe(duplex=False)


    def get_address(self):
        message = "[INFO]: {} Get address.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Get address.")
        address = "http://" + self.host_name + ":" + self.push_port + '/video/' + self.video_name + '.flv'
        return address

    def get_video_len(self):
        result = self._main.recv()
        self._main.close()
        self._proc.close()
        message = "[INFO]: {} Main process communicate closed.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        return result

    def send_chips(self):
        """
        "code": 100 有片段需要发送
                101 无片段需要发送
        """
        const_info = ''
        # print(self.__CONSIST_TABLE)
        time_now = time.time()
        #print(time_now - self.start_time - 4)
        if not os.path.exists(chips_dir):
            return {"code": 101, "result": '', 'const_info': '' if const_info is None else const_info}
        chip_list = [os.path.join(self.code_dir, chips_dir, item) for item in os.listdir(os.path.join(chips_dir))]
        if len(chip_list) == 0:
            return {"code": 101, "result": '', 'const_info': '' if const_info is None else const_info}

        result = []
        for item in chip_list:
            if item not in self.__sended:
                self.__sended.append(item)
                result.append(item)

        message = "[INFO]: {} Send chips: {}.".format(str(datetime.datetime.now()).split('.')[0], ','.join(result))
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        if len(result) == 0:
            return {"code": 101, "result": '', 'const_info': '' if const_info is None else const_info}
        return {"code": 100, "result": result, 'const_info': '' if const_info is None else const_info}

    def initialize(self):

        message = "[INFO]: {} Initialize config.json.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Initialize config.json.")
        self.video_path = None
        self.cap = None
        self.output_dir = None
        with open('config.json', 'r') as f:
            data = json.load(f)

        self.fr_num_frame = data['video_len']
        # 经计算大约1秒长度为31629（以代码中的语音裁剪为基准）
        self.sr_num_frame = data['audio_len']

        self.width = data['width']
        self.height = data['height']

        self.host_name = data['host_name']
        self.push_port = data['push_port']
        self.mysql_user = data['mysql_user']
        self.mysql_password = data['mysql_passwd']
        self.mysql_database = data['mysql_database']
        self.mysql_port = data['mysql_port']
        self.mysql_table = data['mysql_table']

        self.video_root_path = data['video_root_path']
        self.image_root_path = data['image_root_path']
        self.output_root_dir = data['output_dir']
        self.code_dir = data['code_dir']

        if not os.path.exists(self.output_root_dir):
            os.mkdir(self.output_root_dir)
            message = "[INFO]: {} New dir: {}.".format(str(datetime.datetime.now()).split('.')[0], self.output_root_dir)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: New dir:", self.output_root_dir)

        self.api_key = data['api_key']
        self.secret_key = data['secret_key']
        self.dev_pid = data['dev_pid']

        self.__fr_on = data['fr']
        self.__sr_on = data['sr']
        self.threshold = data['threshold']


    def initMysql(self):
        self.mysql = SQLHold(host=self.host_name,
                             user=self.mysql_user,
                             password=self.mysql_password,
                             database=self.mysql_database,
                             port=self.mysql_port)
        message = "[INFO]: {} Mysql init succeed!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Mysql init succeed!")

    def initialize_request(self, data: dict):

        message = "[INFO]: {} Initialize request.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Initialize request.")
        key_words = data['key_words']
        # init mysql
        self.initMysql()
        # end
        # 文件、路径初始化
        audio_dir = os.path.join(self.output_dir, 'wav')
        if not os.path.exists(audio_dir):
            os.mkdir(audio_dir)
            message = "[INFO]: {} New dir: {}.".format(str(datetime.datetime.now()).split('.')[0], audio_dir)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: New dir:", audio_dir)
        # cv初始化
        if 'live' == self.mode:
            self.fetch = FetchStream(self.video_path, self.output_dir)
            self.fetch.start_download()
        # 固定读取图像大小
        self.__refresh()
        face_feature_dict = get_feature(self.mysql, self.video_name)
        key_name, face_feature = get_face_data(face_feature_dict, key_words)

        self.face_detector = FaceDetecter(key_name=key_name,
                                          face_feature=face_feature,
                                          threshold=self.threshold)
        self.key_words = key_words

        self._proc.send(int(self.all_frames / self.fps))

    def __refresh(self):

        message = "[INFO]: {} Refresh arguments!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Refresh arguments!")
        if 'live' == self.mode:
            self.video_path = self.fetch.change_file()
        if self.__fr_on == 'on':
            # capture change!
            self.cap = cv2.VideoCapture(self.video_path)
            # self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            # self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print('---', width, height)
            if not (width == self.width and self.height == height):
                self.__resize = (self.width, int((self.width / width) * height))
            else:
                self.__resize = (self.width, self.height)
            self.all_frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            self.frame_count = 0
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.__fr_all_times = int(self.all_frames / self.fr_num_frame) + 1

        # audio change!
        if self.__sr_on == 'on':
            audio_file = os.path.join(self.output_dir, 'wav', self.video_path.split('/')[-1].split('.')[0] + '.wav')
            self.split_audio(self.video_path, save_file=audio_file) if self.__sr_on == 'on' else None

            wait_to_create(audio_file, "[Audio Cut]", self.video_name)
            with open(audio_file, 'rb') as f:
                message = "[INFO]: {} Read audio file: {}.".format(str(datetime.datetime.now()).split('.')[0], audio_file)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                self.audio = f.read()
        # 这里设置为固定值，这个值为3秒
            self.__len_audio = self.sr_num_frame
            self.__sr_all_times = int(len(self.audio) / self.__len_audio) + 1
            self.__audio_time = get_static_time(self.__len_audio, len(self.audio), self.all_frames, self.fps)
            self.__fr_sr_count = (int(self.__fr_all_times / self.__sr_all_times)) * self.fr_num_frame
            message = "[INFO]: {} Audio times: {}, Video times {}, sr count {}.".format(
                str(datetime.datetime.now()).split('.')[0], self.__sr_all_times, self.__fr_all_times, self.__fr_sr_count)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))

    def split_audio(self, video_path: str, save_file: str) -> None:
        """
        Split audio from video.
        :param video_path: video path.
        :param save_dir: audio path.
        :return: None
        """
        message = "[INFO]: {} Split audio.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Split audio.")
        self.audio_count = 0
        command = ["ffmpeg", "-y", "-i", video_path, "-ac", str(1), "-ar", str(16000), "-loglevel", "error", save_file]
        subprocess.check_output(command, stdin=open(os.devnull), shell=False)

    def get_video_frame(self) -> dict:
        """
        Cut video.
        :return: the first frame and video_split and audio_split
        """

        count = 0
        """
        save_dir = os.path.join(self.output_dir, 'patch')
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
        """
        message = "[INFO]: {} Get video frame.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Get video frame.")
        first_image = None
        # 思路是每次切取固定长度self.fr_num_frame长度的片段作为保存内容，将其audio音频提取并保存,返回:
        start_frame = self.frame_count
        while self.cap.isOpened():
            succeed, frame = self.cap.read()
            if succeed:
                if count == 1:
                    #print(np.shape(frame))
                    first_image = cv2.resize(frame, self.__resize)
                    #print(np.shape(first_image))
                count += 1
                self.frame_count += 1
                # 返回读取的片段
                if count % self.fr_num_frame == 0:
                    # print("[INFO]: count!")
                    end_frame = self.frame_count
                    # end_time = mktime_form(end_frame, self.fps)
                    cut_video_info = {'finished': 'False',
                                      'first_image': first_image,
                                      'start': start_frame,
                                      'end': end_frame}
                    return cut_video_info
            else:
                if 'local' == self.mode:
                    message = "[INFO]: {} Video ID: {}. Finished recognized!".format(
                        str(datetime.datetime.now()).split('.')[0], self.video_path)
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                    # print("[INFO]: Video ID: {}. Finished recognized!".format(self.video_path))
                else:
                    message = "[INFO]: {} Fetch chip finished recognized!".format(str(datetime.datetime.now()).split('.')[0])
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                    # print("[INFO]: Fetch chip finished recognized!")
                self.cap.release()  # 保证正常退出
                return {'finished': 'True',
                        'first_image': '',
                        'start': '',
                        'end': ''}
        if 'live' == self.mode:
            self.cap.release()
            message = "[INFO]: {} 'live' mode refresh!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: 'live' mode refresh!")
            self.__refresh()
            return None
        return {'finished': 'True',
                'first_image': '',
                'start': '',
                'end': ''}

    def get_audio_frame(self) -> list:

        message = "[INFO]: {} Get audio frame.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Get audio frame.")
        if len(self.audio) > self.__len_audio:
            self.audio_count += 1
            audio = self.audio[0: self.__len_audio]
            # 切3秒
            self.audio = self.audio[self.__len_audio:]
        else:
            self.audio_count += 1
            audio = self.audio
            self.audio = self.audio[len(self.audio):]
        return audio

    def speech_recognize(self):

        message = "[INFO]: {} Speech recognize.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Speech recognize.")
        data = self.get_audio_frame()
        # 音频文件为空
        if 0 == len(data):
            message = "[INFO]: {} Audio recognition finished!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: Audio recognition finished!")
            self.__sr_on = 'off'
            return {'mode': 'audio', 'name': '', 'start': '', 'end': ''}

        self.__ad_main.send(data)
        result = self.__ad_main.recv()[0]
        # 检测结果为空
        if '' == result:
            return {'mode': 'audio', 'name': '', 'start': '', 'end': ''}

        name = []
        for item in self.key_words:
            if item in result:
                name.append(item)
        name = ','.join(name) if len(name) > 0 else ''
        return {'mode': 'audio',
                'name': name,
                'start': self.__audio_time * (self.audio_count - 1),
                'end': self.__audio_time}

    def face_recognize(self, image):
        message = "[INFO]: {} Face recognize.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Face recognize.")
        return {'mode': 'video', 'name': self.face_detector._recognize(image)}

    def cut_video(self, cut_video_info: dict) -> dict:

        message = "[INFO]: {} Cut video.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Cut video.")
        save_dir = os.path.join(self.output_dir, 'chips')
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
            message = "[INFO]: {} New dir: {}".format(str(datetime.datetime.now()).split('.')[0], save_dir)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: New dir:", save_dir)

        if self.mode == 'live':
            extension = '.ts'
        else:
            extension = self.video_path[-4:]

        if cut_video_info['mode'] == 'audio':
            start = mktime_sec(cut_video_info['start'])
            end = mktime_sec(cut_video_info['end'])
            end_time = mktime_sec(cut_video_info['start'] + cut_video_info['end']).split('.')[0]
        else:
            start = mktime_form(cut_video_info['start'], self.fps)
            end = str((cut_video_info['end'] - cut_video_info['start']) / self.fps)
            end_time = mktime_form(cut_video_info['end'], self.fps).split('.')[0]

        output_file = os.path.join(save_dir,
                                   cut_video_info['mode'] + '#' + start.split('.')[0].replace(':', '-') + '#' +
                                   end_time.replace(':', '-') + '#' + cut_video_info['name'] + '#'
                                   + self.video_name + extension)
        command = ["ffmpeg", "-loglevel", "error", "-y", "-ss",
                   start, "-i", self.video_path, "-t",
                   end, "-c:v", "libx264", "-c:a", "aac",
                   "-ar", "44100", output_file]

        # shell变量是否需要开启取决于命令command的类型，str类型的command需要使用shell=True，list类型的command使用shell=False
        message = "[INFO]: {} ffmpeg.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        subprocess.check_output(command, stdin=open(os.devnull), shell=False)

        result = {'video_path': output_file}

        # 由于subprocess是启用另外一个进程执行任务，所以得等待到文件创建为止
        wait_to_create(output_file, "[Cut Video]", self.video_name)

        return result

    def record(self, cut_video_info: dict):
        """
        Report to mysql database.
        :param cut_video_info: result of predict.
        :return: update of predict.
        """

        message = "[INFO]: {} Record.".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Record.")
        insert_command = f"insert into {self.mysql_table} " \
                         f"(video_id, start, end, person_name, save_file, mode) " \
                         f"values(\'{self.video_path}\', " \
                         f"\'{cut_video_info['start']}\', " \
                         f"\'{cut_video_info['end']}\', " \
                         f"\'{cut_video_info['name']}\'," \
                         f" \'{cut_video_info['video_path']}\'," \
                         f" \'{cut_video_info['mode']}\' )"

        try:
            self.mysql.execute_command(insert_command)
        except pymysql.err.IntegrityError:
            message = "[Warning]: {} Record: {} is exists!".format(str(datetime.datetime.now()).split('.')[0],
                                                               cut_video_info['video_path'])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'warning-' + self.video_name + '.log'))
            # print("[Warning]: This chip is exists!")

        return cut_video_info

    def run(self):

        # initialize resource
        message = "----[INFO]: {} Run.----".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
        # print("[INFO]: Run.")
        self.initialize_request(self.data)
        video_frame_info = {}
        is_run = True
        # 切片时间记录字，用于记录切片帧长的变量，最少包含一个片段结尾帧序号
        cut_time = [0]
        # 用于记录上次识别的结果
        re_name = ''
        try:
            while is_run:
                # 后台显示完成进度
                if not 0 == self.all_frames:
                    print("[INFO]: ID:{} : {}".format(self.video_name,
                                                      "#" * int(self.frame_count * 10 / self.all_frames)))
                video_frame_info.update({'mode': 'video'})
                video_frame_info.update(self.get_video_frame())

                # 判断退出条件
                if not self.cap.isOpened() and 'live' == self.mode:
                    self.cap.release()
                    message = "[INFO]: {} 'live' mode refresh!".format(str(datetime.datetime.now()).split('.')[0])
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                    # print("[INFO]: 'live' mode refresh!")
                    self.__refresh()
                    is_run = True
                elif self.cap.isOpened():
                    is_run = True
                else:
                    message = "[INFO]: {} Quit!".format(str(datetime.datetime.now()).split('.')[0])
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                    # print("[INFO]: Quit!")
                    is_run = False

                # 如果读出来为空帧则跳过循环
                if video_frame_info is None:
                    continue
                # 如果读完则跳过循环
                if video_frame_info['finished'] == 'True':
                    continue
                image = video_frame_info['first_image']
                ad_result = None
                vd_result = self.face_recognize(image) if self.__fr_on == 'on' else None
                # 加个判断，当达到一个视频帧对某个数取余为0时进行音频检测，这样使音频尽量贴近真实检测时间
                # print(self.frame_count)
                if self.__sr_on == 'on' and (self.frame_count % self.__fr_sr_count == 0):
                    ad_result = self.speech_recognize()
                # 此段代码逻辑为先缓存所有chips的start信息和end信息，但是每次pop最后一个end，这样达到头尾记录片段信息的功能
                # 在下一次检测不到人脸的时候开始裁剪或者紧接帧换人脸时开始裁剪
                if (vd_result is not None) and (not '' == vd_result['name']):
                    # 这里要保证len(cut_time) >= 1
                    assert len(cut_time) >= 1, "[ERROR]: Code error,'len(cut_time) >= 1'!"
                    # 合并切片
                    if video_frame_info['end'] - cut_time[-1] <= self.fr_num_frame:
                        # 连续片段换人裁剪视频
                        message = "[INFO]: {} Emerge chip.".format(str(datetime.datetime.now()).split('.')[0])
                        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                        # print("[INFO]: Emerge chip.")
                        if not '' == re_name and not vd_result['name'] == re_name:
                            message = "[INFO]: {} Record video, Change people {}.".format(str(datetime.datetime.now()).split('.')[0], re_name)
                            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                            # print("[INFO]: Record video.")
                            re_name = vd_result['name']
                            # 记录当前片段的帧
                            start_now = video_frame_info['start']
                            end_now = video_frame_info['end']
                            # 首先是更新帧数，使cut_video能剪裁
                            video_frame_info.update({'start': cut_time[0], 'end': cut_time[-1]})
                            # 产生video_path
                            video_frame_info.update(self.cut_video(video_frame_info))
                            # 第二次更新为时间信息，用于存入数据库
                            video_frame_info.update({'start': mktime_form(cut_time[0], self.fps),
                                                     'end': mktime_form(cut_time[-1], self.fps)})
                            self.record(video_frame_info)
                            # 切片完成即清除切片时间记录字
                            cut_time.clear()
                            cut_time = [start_now - 1]
                            # 第三次更新是还原记录段
                            video_frame_info.update({'start': start_now,
                                                     'end': end_now})
                        # 如果第一帧里检测到人脸则记录人脸名称，记录切片信息
                        elif '' == re_name:
                            re_name = vd_result['name']
                    # 其实上三步均有次操作，此处简写，请仔细想逻辑，经测试这段代码没问题
                    # 这里如果检测到大于最后结尾帧则将首帧去掉，因为不可能出现下次远点开始时有前面片段信息的记录
                    # 此时让cut_time pop出最后一个时间信息，这里是为了防止仅有一个片段时起始位置偏移的错误
                    cut_time.pop()
                    cut_time.append(video_frame_info['start'])
                    cut_time.append(video_frame_info['end'])
                    video_frame_info.update({'name': vd_result['name']})
                    # 限制裁剪片段的长度此处限制在3s
                    if cut_time[-1] - cut_time[0] >= self.__fr_sr_count:
                        message = "[INFO]: {} Record video, max len.".format(str(datetime.datetime.now()).split('.')[0])
                        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                        # print("[INFO]: Record video.")
                        start_now = video_frame_info['start']
                        # 首先是更新帧数，使cut_video能剪裁
                        video_frame_info.update({'start': cut_time[0], 'end': cut_time[-1]})
                        # 产生video_path
                        video_frame_info.update(self.cut_video(video_frame_info))
                        # 第二次更新为时间信息，用于存入数据库
                        video_frame_info.update({'start': mktime_form(cut_time[0], self.fps),
                                                 'end': mktime_form(cut_time[-1], self.fps)})
                        self.record(video_frame_info)
                        # 切片完成即清除切片时间记录字
                        cut_time.clear()
                        cut_time.append(start_now - 1)
                else:
                    if len(cut_time) > 1:
                        message = "[INFO]: {} Record video.".format(str(datetime.datetime.now()).split('.')[0])
                        write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                        # print("[INFO]: Record video.")
                        start_now = video_frame_info['start']
                        # 首先是更新帧数，使cut_video能剪裁
                        video_frame_info.update({'start': cut_time[0], 'end': cut_time[-1]})
                        # 产生video_path
                        video_frame_info.update(self.cut_video(video_frame_info))
                        # 第二次更新为时间信息，用于存入数据库
                        video_frame_info.update({'start': mktime_form(cut_time[0], self.fps),
                                                 'end': mktime_form(cut_time[-1], self.fps)})
                        self.record(video_frame_info)
                        # 切片完成即清除切片时间记录字
                        cut_time.clear()
                        cut_time.append(start_now - 1)

                if (ad_result is not None) and (not '' == ad_result['name']):
                    message = "[INFO]: {} Record audio.".format(str(datetime.datetime.now()).split('.')[0])
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
                    # print("[INFO]: Record audio.")
                    ad_result.update(self.cut_video(ad_result))
                    ad_result.update(
                        {
                            'start': mktime_sec(ad_result['start']),
                            'end': mktime_sec(ad_result['start'] + ad_result['end'])
                        }
                    )
                    self.record(ad_result)
        except pymysql.err.OperationalError:
            self.mysql.close()
            del self.mysql
            message = "[Warning]: Mysql connect failed, re-connect!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'warning-' + self.video_name + '.log'))
            # print("[Warning]: Mysql connect failed, re-connect!")
            self.initMysql()

        finally:
            message = "----[INFO]: {} Process {} finished!----".format(str(datetime.datetime.now()).split('.')[0], self.video_name)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            print("-" * 20, "{} finished!".format(self.video_name), "-" * 20)
            self.release()

    def terminate(self) -> None:
        self.release()
        super(CutServer, self).terminate()

    def release(self):
        try:
            # 这里需要将cap,mysql初始化为None，否则就是进程变量无法通信而引发报错
            if self.cap is not None:
                self.cap.release()
            if self.mysql is not None:
                self.mysql.close()
            self.__ad_main.send('stop')
            if self.speech_detector is not None:
                sr_pid = self.speech_detector.pid
                self.speech_detector.terminate()
                os.kill(sr_pid, signal.SIGSTOP)
                self.__ad_main.close()
                self.__ad_proc.close()
            message = "[INFO]: {} Release finished.".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run-' + self.video_name + '.log'))
            # print("[INFO]: Release finished.")
        except Exception as e:
            err_message = traceback.format_exc()
            message = "[ERROR]: {} Release error, we don't know this error!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error-' + self.video_name + '.log'))
            write_log(message=err_message, file_=os.path.join(LOG_DIR, 'error-' + self.video_name + '.log'))
            # print("[ERROR]: Release error, we don't know this error!")

    @staticmethod
    def server_start_print():
        print("[INFO]:Start cut video web server.")

    @staticmethod
    def vdpreview(data):
        video_path = data['video_path']
        video_list = edict()
        dirfilepaths = os.listdir(os.path.join(os.getcwd(), video_path))
        for filepath in dirfilepaths:
            filepath = os.path.join(video_path, filepath)
            video_list[filepath] = str(filepath)
        return {'video_path': video_path, 'video_list': video_list}


def start_web_server():

    AsyncIOMainLoop().install()
    app = tornado.web.Application([
        (r'/vdpreview', WebHandler, {'runner': CutServer.vdpreview}),
        (r'/vdfilter', CutHandler, {'runner': CutServer}),
        (r'/addfeature', AddHandler),
    ], debug=True
    )
    http_server = tornado.httpserver.HTTPServer(app)
    http_server.listen(9999)
    CutServer.server_start_print()
    tornado.ioloop.IOLoop.current().start()

