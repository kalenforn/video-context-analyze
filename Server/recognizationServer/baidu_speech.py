import os
import json
import base64
import datetime
import traceback

import multiprocessing as mp

from urllib.request import urlopen
from urllib.request import Request
from urllib.error import URLError
from urllib.parse import urlencode

from tools.log import write_log

LOG_DIR = os.path.join('log', 'sr')
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)

class BaiduSRC(mp.Process):

    def __init__(self, api_key, secret_key, dev_pid, pipe,
                 format_: str = 'wav',
                 cuid: str = '123456PYTHON',
                 rate: int = 16000,
                 as_url: str = 'http://vop.baidu.com/server_api',
                 scope: str = 'audio_voice_assistant_get',
                 token_url: str = 'http://openapi.baidu.com/oauth/2.0/token'
                 ):
        super(BaiduSRC, self).__init__()
        self.api_key = api_key
        self.secret_key = secret_key
        self.format = format_
        self.cuid = cuid
        # 采样率
        self.rate = rate  # 固定值

        self.dev_pid = dev_pid  # 1537 表示识别普通话，使用输入法模型。根据文档填写PID，选择语言及识别模型
        self.as_url = as_url
        self.scope = scope  # 有此scope表示有asr能力，没有请在网页里勾选，非常旧的应用可能没有

        """  TOKEN start """

        self.token_url = token_url
        self.token = self.fetch_token()

        # 用于进程通信.
        self.__pipe = pipe

    def fetch_token(self):

        message = "[INFO]: {} Fetch token!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        params = {'grant_type': 'client_credentials',
                  'client_id': self.api_key,
                  'client_secret': self.secret_key}
        post_data = urlencode(params)
        post_data = post_data.encode('utf-8')
        req = Request(self.token_url, post_data)
        try:
            message = "[INFO]: {} Request finished!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
            f = urlopen(req)
            result_str = f.read()
        except URLError as err:
            result_str = err.reason
            message = "[ERROR]: {} Token http response reason : {}.".format(str(datetime.datetime.now()).split('.')[0],
                                                                          str(result_str))
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            print('[ERROR] Token http response reason :', str(result_str))
            # print('token http response http code : ' + str(err.code)
        result_str = result_str.decode()

        # print(result_str)
        result = json.loads(result_str)
        # print(result)
        if ('access_token' in result.keys() and 'scope' in result.keys()):
            if self.scope and (not self.scope in result['scope'].split(' ')):  # SCOPE = False 忽略检查
                message = "[ERROR]: {} Scope is not correct!".format(
                    str(datetime.datetime.now()).split('.')[0])
                write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                print('[ERROR]: Scope is not correct!')
            # print('SUCCESS WITH TOKEN: %s ; EXPIRES IN SECONDS: %s' % (result['access_token'], result['expires_in']))
            return result['access_token']
        else:
            message = "[ERROR]: {} Maybe API_KEY or SECRET_KEY not correct: access_token or scope not found in token response.".format(
                str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            print('[ERROR]: Maybe API_KEY or SECRET_KEY not correct: access_token or scope not found in token response')

    def run(self):

        message = "[INFO]: {} Run!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))

        repeat = 0
        while True:
            try:
                speech_data = self.__pipe.recv()
            except EOFError as e:
                # 这里有个bug我解决不好，暂时用这种限定重复上限的方式break程序避免错误，连续进入20次收到error的信息时break
                repeat += 1
                if repeat > 20:
                    message = "[ERROR]: {} Nothing received! Out of max repeat times! Break!\n".format(str(datetime.datetime.now()).split('.')[0])
                    message += "[ERROR]: {} \n".format(str(datetime.datetime.now()).split('.')[0])
                    message += traceback.format_exc()
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                    print("[ERROR]: Nothing received! Out of max repeat times! Break!")
                    break
                message = "[Warning]: {} Nothing received!".format(str(datetime.datetime.now()).split('.')[0])
                write_log(message=message, file_=os.path.join(LOG_DIR, 'warning.log'))
                print("[Warning]: Nothing received!")
                continue
            # 避免的时候如果出现收到数据则更新
            repeat = 0
            if speech_data == 'stop':
                break
            length = len(speech_data)
            if length == 0:
                message = "[ERROR]: {} Data length 0 bytes!".format(str(datetime.datetime.now()).split('.')[0])
                write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                print("[ERROR]: Data length 0 bytes!")
                self.__pipe.send([''])
            # for i in range(3):
            else:
                speech = base64.b64encode(speech_data)
                speech = str(speech, 'utf-8')
                params = {'dev_pid': self.dev_pid,
                          # "lm_id" : LM_ID,    #测试自训练平台开启此项
                          'format': self.format,
                          'rate': self.rate,
                          'token': self.token,
                          'cuid': self.cuid,
                          'channel': 1,
                          'speech': speech,
                          'len': length
                          }
                post_data = json.dumps(params, sort_keys=False)
                # print post_data
                req = Request(self.as_url, post_data.encode('utf-8'))
                req.add_header('Content-Type', 'application/json')
                try:
                    f = urlopen(req)
                    result_str = f.read()
                    message = "[INFO]: {} Request finished!".format(str(datetime.datetime.now()).split('.')[0])
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
                except URLError as err:
                    result_str = err.reason
                    message = "[ERROR]: {} Asr http response reason : {}.".format(str(datetime.datetime.now()).split('.')[0], str(result_str))
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                    print('[ERROR] Asr http response reason :', str(result_str))
                result_str = str(result_str, 'utf-8')
                result_str = json.loads(result_str)

                if 'result' in result_str:
                    print(result_str['result'])
                    self.__pipe.send(result_str['result'])
                else:
                    self.__pipe.send([''])

            message = "[INFO]: {} Sr finished!".format(str(datetime.datetime.now()).split('.')[0])
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))



