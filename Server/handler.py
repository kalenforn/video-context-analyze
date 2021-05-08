import tornado.web

import json

class WebHandler(tornado.web.RequestHandler):
    def initialize(self, runner):
        self.runner = runner

    def post(self):
        print("post")

        data = self.request.body.decode('utf-8')
        # 这里可能会出现传过来的json加载一次不能转为dict，故多加载几次直到转为dict为止
        while not isinstance(data, dict):
            data = json.loads(data)
        if data:
            #print(data)
            result = self.runner(data)  # 这里是基于pytorch写的，其他框架请参考输出tensor转list的方法
        else:
            self.runner()
        assert isinstance(result, dict), "[ERROR]:WebHandler's attribute runner must return a dict!"
        self.write(result)
