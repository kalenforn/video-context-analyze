import os
import json
import signal
import datetime

import tornado.web

from tools.log import write_log

LOG_DIR = os.path.join('./log', 'cutHandler')
if not os.path.exists(os.path.join('log', 'cutServer')):
    os.mkdir(os.path.join('log', 'cutServer'))
# 总进程控制器，用于客户端控制某个进程
Runner_IP_dict = dict()
Count = 0

class Runner:
    def __init__(self, data: dict):
        self.process = data['class'](data['data'])

    def start(self):
        self.process.start()

    def close(self):
        pid = self.process.pid
        self.process.terminate()
        os.kill(pid, signal.SIGSTOP)

    def address(self):
        return self.process.get_address()

    def get_chips(self):
        return self.process.send_chips()

    def get_video_len(self):
        return self.process.get_video_len()

def address(runner: dict):

    address = []
    for item in runner.values():
        address.append(item.address())
    return address

def get_video_len(runner: dict):

    result = {}
    for item in runner:
        result.update({item: runner[item].get_video_len()})
    return result

class CutHandler(tornado.web.RequestHandler):
    global Runner_IP_dict

    def initialize(self, runner):

        self.runner_class = runner


    def new_one_runner(self, data: dict):
        """
        以id的方式记录每个process，将每个process记录到一个dict内，以id的方式存取
        :param data: {'id': process target, 'data': runner data, 'class': runner class, 'count': runner counter}
        :return: None
        """
        id = data['id']
        data['data'].update({'ip': self.request.remote_ip})
        runner = Runner(data)
        self.Runner_dict.update({id: runner})
        runner.start()
        message = "[INFO]: {} Process {} start! IP: {}".format(str(datetime.datetime.now()).split('.')[0], id, self.request.remote_ip)
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        # print("[INFO]: {} process start!".format(id))

    def new_multiply_runner(self, data: dict):

        for item in data:
            self.new_one_runner(data[item])

    def close_one_process(self, id: str):

        if len(self.Runner_dict) <= 0:
            message = "[ERROR]: {} There are no processes! IP: {}".format(str(datetime.datetime.now()).split('.')[0], self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            # print("[ERROR]: There are no processes!")
            return {'status': 'Failed',
                    'message': "No process has been created!"}

        if self.Runner_dict[id].process.is_alive():
            self.Runner_dict[id].close()
            self.Runner_dict.pop(id)
            message = "[INFO]: {} Process {} closed! IP: {}".format(str(datetime.datetime.now()).split('.')[0], id, self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
            print("[INFO]: {} process closed!".format(id))
            return {'status': 'Stop',
                    'message': 'Process close succeed!',
                    "keys": list(self.Runner_dict.keys())}
        else:
            self.Runner_dict.pop(id)
            message = "[INFO]: {} Process {} is not alive! IP: {}".format(str(datetime.datetime.now()).split('.')[0], id, self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
            print("[INFO]: {} process is not alive!".format(id))
            return {'status': 'Stop',
                    'message': "The remaining process is killed!"}

    def close_all_process(self):

        if len(self.Runner_dict) <= 0:
            message = "[ERROR]: {} There are no processes! IP: {}".format(str(datetime.datetime.now()).split('.')[0], self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            # print("[ERROR]: There are no processes!")
            return {'status': 'Failed',
                    'message': "No process has been created!"}

        for id in list(self.Runner_dict.keys()):
            self.close_one_process(id)
        message = "[INFO]: {}  All processes closed! IP: {}".format(str(datetime.datetime.now()).split('.')[0], self.request.remote_ip)
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        # print("[INFO]: All processes closed!")
        return {'status': 'Stop',
                'message': "All processes closed!",
                "keys": list(self.Runner_dict.keys())}

    def prepare(self):
        data = self.request.body.decode('utf-8')
        # 这里可能会出现传过来的json加载一次不能转为dict，故多加载几次直到转为dict为止
        while not isinstance(data, dict):
            data = json.loads(data)

        if self.request.remote_ip not in Runner_IP_dict:
            Runner_IP_dict.update({self.request.remote_ip: {}})
        # ip定位控制器
        self.Runner_dict = Runner_IP_dict[self.request.remote_ip]
        self.data = {}
        self.mode = data['mode']
        self.video_mode = data['video_mode']
        self.video_address = data['video_address'] if data['video_mode'] == 'live' else ''
        for i, item in enumerate(data['id']):
            self.data.update({
                item: {'video_name': data['video_name'][i] if 'local' == data['video_mode'] else '',
                       'key_words': data['key_words'],
                       'video_mode': data['video_mode'],
                       'video_address': data['video_address'][i] if data['video_mode'] == 'live' and self.mode == 'new' else ''
                }
            })
        if len(self.data) <= 0:
            message = "[ERROR]: {} Receive data error! IP".format(str(datetime.datetime.now()).split('.')[0], self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            # print("[ERROR]: receive data error!")
            raise ValueError("[ERROR]:Value data less have 1 elements,but get 0 elements!")
        #print(self.data)

        ## print("[INFO]: New {} number of process!".format(len(data)))

    def chips_deal(self):
        result_all = {}
        const_all = {}
        for item in self.data.keys():
            if item not in self.Runner_dict.keys():
                message = "[ERROR]: {} Process {} hasn't created! IP: {}".format(str(datetime.datetime.now()).split('.')[0], item, self.request.remote_ip)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                # print("[ERROR]: {} process hasn't created!".format(item))
                return{'status': 'Failed',
                            'message': "{} process hasn't created!".format(item)}
            if not self.Runner_dict[item].process.is_alive():
                message = "[INFO]: {}  Process {} has finished! IP: {}".format(str(datetime.datetime.now()).split('.')[0], item, self.request.remote_ip)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
                # print("[INFO]: {} process has finished!".format(item))
                result = ['Finished']
                result_all.update({item: result})
            else:
                result = self.Runner_dict[item].get_chips()
                if result['code'] == 101:
                    const_all.update({item: result['const_info']})
                    print("[INFO]: No chips!")
                elif result['code'] == 100:
                    result_all.update({item: result['result']})
                    const_all.update({item: result['const_info']})

        if len(result_all) <= 0:
            return {
                'status': 'Push',
                'message': 'No chips!',
                'chips': '',
                'const_info': const_all
            }
        return {
                'status': 'Push',
                'message': 'New chips!',
                'chips': result_all,
                'const_info': const_all
            }

    def new_deal(self):
        message = "[INFO]: {} Client request. IP: {}".format(str(datetime.datetime.now()).split('.')[0], self.request.remote_ip)
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        last_num = len(self.Runner_dict)  # 记录上一时刻进程的个数（路数）
        for item in self.data.keys():
            # print('data')
            if item in self.Runner_dict.keys() and self.Runner_dict[item].process.is_alive():
                message = "[ERROR]: {} Don't repeat the process of {}! IP:".format(str(datetime.datetime.now()).split('.')[0],
                                                                          item, self.request.remote_ip)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                # print("[ERROR]: Don't repeat the process of {}!".format(item))
                return {'status': 'Failed',
                            'message': "Don't repeat the process of {}!".format(item)}
            self.new_one_runner({'class': self.runner_class,
                                 'data': self.data[item], 'id': item})
        # 用当前状态的路数减去上一个状态的路数，差值若等于data的长度则创建进程成功，否则失败
        if len(self.Runner_dict) - last_num == len(self.data):
            message = "[INFO]: {} New {} number of process! IP: {}".format(str(datetime.datetime.now()).split('.')[0], len(self.data), self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
            # print("[INFO]: New {} number of process!".format(len(self.data)))
            if 'live' == self.video_mode:
                return {'status': 'Initing',
                            'message': "New process succeed!",
                            'Live-address': self.video_address}
            else:
                return {'status': 'Initing',
                            'message': "New process succeed!",
                            'Live-address': address(self.Runner_dict),
                            'all_frame': get_video_len(self.Runner_dict)}
        else:
            message = "[ERROR]: {} Number of {} processes hasn't created! IP: {}".format(str(datetime.datetime.now()).split('.')[0],
                                                                           len(self.data) - (len(self.Runner_dict) - last_num), self.request.remote_ip)
            write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
            # print("[ERROR]: {} processes hasn't created!".format(len(self.data) - (len(Runner_dict) - last_num)))
            for item in self.data.keys():
                if item not in self.Runner_dict.keys():
                    message = "[ERROR]: {} Process {} hasn't create! IP: {}".format(
                        str(datetime.datetime.now()).split('.')[0], self.data[item]['video_address'], self.request.remote_ip)
                    write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                    # print("[ERROR]: {} hasn't create!".format(self.data[item]['video_address']))
            return {'status': 'Failed',
                        'message': "Process create error!"}

    def close_deal(self):

        for item in self.data.keys():
            if item not in self.Runner_dict.keys():
                message = "[ERROR]: {} Process {} hasn't create! IP: {}".format(
                    str(datetime.datetime.now()).split('.')[0], item, self.request.remote_ip)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'error.log'))
                # print("[ERROR]: {} process hasn't created!".format(item))
                return {'status': 'Failed',
                            'message': "{} process hasn't created!".format(item)}
            else:
                message = "[INFO]: {} Process {} has stopped! IP: {}".format(str(datetime.datetime.now()).split('.')[0], item, self.request.remote_ip)
                write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
                # print("[INFO]: {} process has stopped!".format(item))
                return self.close_one_process(item)

    def post(self):
        print("[INFO]: Get request!")

        if self.mode == 'new':
            self.write(self.new_deal())
        elif self.mode == 'post':
            self.write(self.chips_deal())
        elif self.mode == 'stop':
            self.write(self.close_deal())
        elif self.mode == 'astop':
            self.write(self.close_all_process())



