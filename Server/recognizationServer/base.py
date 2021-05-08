import time

def total_time(func):
    """
    Calculate the running time of the function
    :param func: the function need to been calculated
    :return: func's result
    """
    def call_fun(*args, **kwargs):
        start_time = time.time()
        f = func(*args, **kwargs)
        end_time = time.time()
        print('[INFO]:%s() run time:%ss' % (func.__name__, end_time - start_time))
        return f
    return call_fun

class BaseRecognition():

    def __init__(self, model_path: str, schema='pytorch', port=9999):
        super(BaseRecognition, self).__init__()
        #print(schema)

        assert schema in ['dlib', 'pytorch', 'tensorflow', 'snowboy'], "[ERROR]: Argument of 'mode' must in " \
                                                                "['dlib', 'pytorch', 'tensorflow']!"
        self.schema = schema
        if schema == 'dlib':
            self.model = None
        elif schema == 'pytorch':
            import torch
            self.model = torch.load(model_path)
            self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
        elif schema == 'tensorflow':
            import tensorflow as tf
            ######## 加载的是pb文件，包括模型结构和weight参数
            # image resolution: 224 * 224 * 3
            self.input_placeholder = tf.placeholder(name='img_inputs',
                                                    shape=PLACE_HOLDER_SHAPE, dtype=tf.float32)
            self.session = tf.Session()
            with tf.python.platform.gfile.FastGFile(model_path, 'rb') as f:
                graph_def = tf.GraphDef()
                graph_def.ParseFromString(f.read())
                self.session.graph.as_default()
                tf.import_graph_def(graph_def, name='')
        elif schema == 'snowboy':
            pass

    @staticmethod
    def _server_start_print(self):
        """
        Print information about web server startup
        :return: None
        """
        pass

    # @total_time
    def _recognize(self, _input: dict) -> list:
        """
        starting recognize.
        :param _input: a dict, key word is 'input'.
        :return: recognize person's name.
        """
        raise AssertionError("[ERROR]: Empty function!")

    def initialize(self, data: dict) -> dict:
        raise AssertionError("[ERROR]: Empty function!")

    def closs(self):
        if self.schema == 'tensorflow':
            self.session.close()
        else:
            pass



