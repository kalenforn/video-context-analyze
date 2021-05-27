# 进程控制器

在代码结构中，进程控制器所处的位置是```Server/videoProcessServer/cutHandler.py```，该方案中，采用客户端IP进行客户端唯一标识ID，防止多用户同时请求同一视频导致的多客户端互锁情况。

## 进程变量存储方式

代码中的

```python
Runner_IP_dict = dict()
```

用于记录所有进程，以python的字典数据类型保存结果，正常运行时值为：

```json
{ip1:
   {video_id1: process,
    video_id2: process, ...}，
 ip2:
    {video_id1: process,
    video_id2: process, ...},
 ...}
```

## 进程变量Runner类

```python
class Runner:
    def __init__(self, data: dict):
        self.process = data['class'](data['data'])

    def start(self):
        # 开启进程
        self.process.start()

    def close(self):
        # 关闭进程
        pid = self.process.pid
        self.process.terminate()
        os.kill(pid, signal.SIGSTOP)

    def address(self):
        # 获取推流地址
        return self.process.get_address()

    def get_chips(self):
        # 获取切片信息
        return self.process.send_chips()

    def get_video_len(self):
        # 获取视频长度
        return self.process.get_video_len()
```

该类型定义了Runner_IP_dict里对应的每个进程变量，其初始化的方式是通过字典```data``来传递，该类型保证了对进程的开启和关闭以及通过该类的封装调用获取进程产生的切片数据

## web接口+进程控制器逻辑

```python
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
        ...

    def chips_deal(self):
        ...

    def new_deal(self):
        ...

    def close_deal(self):
        ...

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
```

该类是web端监听的主要调用体，每次客户端发送post请求给服务端时，其会调用post方法，客户端可对服务端进行四种操作：new新建进程（可多开）、post查询是否有新片段、stop-one停止单个进程、stop-all停止所有进程。

**首先来看客户端请求后服务端的准备函数**

```python
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
```

客户端在发送post请求时，服务端首先会调用这个函数作为数据解封装的过程，这个过程中，首先将post请求字段转为json字符串，然后**获取客户端IP**，此时将客户端IP绑定，以防止多用户同时请求同一视频读写错误，然后将构造data字段，由于客户端为了降低传输时延发送的数据是简略数据，需要在服务端增广后才能构建识别进程，故而有了后续的for操作。

接下来服务器将会调用post函数，post方法将会在每一次怕post请求时调用一次且该类**只有**在每一次post请求时才会被实例化在post执行完之后会被释放，所以此时需要一个全局变量记录进程变量。由于需求为**进程控制器控制每个异步的视频处理进程**，这就要求进程控制器与视频处理进程异步，此处采用multiprocess库中的Process类来实现**视频处理进程和控制进程的异步运行**，进程池pool所使用的是一种同步运行的方式，无法满足控制器对视频处理进程的异步控制。此处又采用高效的tornado**异步web框架**，实现了**多用户的高并发**。

下面将依次讲解不同请求字段的含义

**new_deal()函数**

```python
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
```

该函数首先会记录上一个时刻该用户的进程总数last_num，目的是用于判断进程是否创建成功，该函数会根据预处理的参数self.data内的id字段查询用户进程中是否已经存在该进程，若存在则打印和返回错误信息并终止创建，在创建完成之后其会根据last_num判断所有进程是否创建成功，若有未创建成功的则返回失败。

**chip_deal()函数**

```python
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
```

该函数根据请求得到的self.data字段查询id值，然后对对应的进程进行get_chip()操作，这个操作将会获取服务器上生成的视频片段地址，然后客户端需要通过ftp的方式下载对应的视频。

**close_deal()函数**

```python
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
```

该函数根据id字段对不同视频进行关停。

**综上所述：**

​	所有的控制逻辑都是与video_id相结合的，也就是客户端的请求字段中id字段必不可少，id决定了后台中的总控制对象，这种查询方法我将其成为开锁法，类似公钥开门，客户端手持公钥，将公钥返回给服务端后，服务端根据公钥对每个不同的进程进行控制操作。



## 关于python的mp库的一些简单手稿

在本项目中，本人尝试过使用pool进程池的方式启动该进程，但项目需求为控制器对进程异步控制，而pool方式的进程启动无论如何都会对部分进程及主进程阻塞，导致控制进程无法与视频处理进程异步运行，所以采用Process的方式，让视频处理进程异步运行。

此间本人遇到过很多错误，其中最重要的一条是python的多进程编程中对资源类型数据变量的初始化问题，这个问题对于初次接触python多进程编程的人来说很难解决，因为编译器报的错全是runtime错误，也无法调试。

问题是这样的，当你的多进程需要调用一些资源类数据时（如opencv中读取视频文件的错做），如果你将这个变量放在主进程通过传参的方式传递给多进程行不行？那如果你现在定义了一个Process类的子类，你直接将其放在__init\_\_()方法里行不行？这两个问题归根结底就是在问，你的这个资源类型数据的初始化应该放在那个位置。

如：

```python
# process1 we write the cap in main:
class MyProcess(mp.Process)
	def __init__(self, cap):
        self.cap = cap
    def run(self):
        flag = true
        count = 0
        while flag:
            flag, _ = self.cap.read()
            count += 1
            print(count)
def main():
	cap = cv2.VideoCapture('xxx.mp4')
    process1 = MyProcess(cap)
    process1.start()
    sleep(20)
    process1.join()
    process1.close()
```

这两个问题的答案是不行，因为本人对这两种方案都做过尝试，结果是都报runtime错误，读者可以将上述代码跑跑试一下，你会得到runtime错误，为什么会这样呢？其实主要的原因在于mp库在进程创建的时候会对其中所包含的资源进行序列化操作，而这个序列化操作只对一些简单的静态变量(int, str,double)类型数据有效，对这种设计资源数据是无法序列化的。

那问题来了，如果这个进程他就是需要这些资源变量我该如何操作呢？其实解决方案很简单，就是换个位置初始化这些变量，既然已经知道mp库只能序列化简单类型变量，那我就把简单类型的变量保留下来，在他序列化完以后再初始化资源变量就好了，而mp库中的Process类的序列化只会在run方法被执行也就是调用process.start()方法时进行，也就是说你可以在两个地方对资源类数据进行初始化一个是run方法里，另一个是start方法里，那么上述代码可以改为：

```python
# process2 we write the cap in run:
class MyProcess(mp.Process)
	def __init__(self, video_path):
        self.video_path = video_path
    def run_init(self):
        self.cap = cv2.VideoCapture(self.video_path)
    def run(self):
        flag = true
        count = 0
        while flag:
            flag, _ = self.cap.read()
            count += 1
            print(count)
def main():
	video_path = "xxx.mp4"
    process2 = MyProcess(video_path)
    process2.start()
    sleep(20)
    process2.join()
    process2.close()
```

此时的代码会完整的执行，也就是改变你代码中初始化资源类数据的位置可以解决掉一些你多进程编程中出现的runtime错误



[项目地址](https://github.com/kalenforn/video-context-analyze.git)

