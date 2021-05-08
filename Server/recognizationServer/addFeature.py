import os
import cv2
import dlib
import json

import tornado.web

import numpy as np

from Server.videoProcessServer.mysqlTools import SQLHold

class AddHandler(tornado.web.RequestHandler):

    def initialize(self):
        super(AddHandler, self).initialize()

    def prepare(self):
        with open('config.json', 'r') as f:
            data = json.load(f)
            data_dir = data['image_root_path']
            self.mysql = SQLHold(host=data['host_name'], user=data['mysql_user'], password=data['mysql_passwd'],
                                 database=data['mysql_database'], port=data['mysql_port'])
        currentpath = os.path.dirname(os.path.abspath(__file__))
        self.detector = dlib.cnn_face_detection_model_v1(
            currentpath + '/models/mmod_human_face_detector.dat')
        self.face_rec_model = dlib.face_recognition_model_v1(currentpath + '/models/face_model.dat')
        self.shape_predictor = dlib.shape_predictor(currentpath + '/models/face_alignment.dat')
        self.cascade = cv2.CascadeClassifier(currentpath + "/models/haarcascade_frontalface_alt.xml")

        data = self.request.body.decode('utf-8')
        # 这里可能会出现传过来的json加载一次不能转为dict，故多加载几次直到转为dict为止
        while not isinstance(data, dict):
            data = json.loads(data)

        self.image_path = os.path.join(data_dir, data['image_path'])

    def post(self):
        if not os.path.exists(self.image_path):
            print("[INFO]: ", self.image_path, "file does not exists!")
            self.write({'status': 'Failed',
                        'message': 'Insert face failed!'})
            return
        image = cv2.imdecode(np.fromfile(self.image_path, dtype=np.uint8), -1)
        name = self.image_path.split('/')[0]

        b, g, r = cv2.split(image)
        image_rgb = cv2.merge([r, g, b])
        face_local = self.detector(image_rgb, 1)
        if len(face_local) > 1:
            print(self.image_path, "has more than one face")
            self.write({'status': 'Failed',
                            'message': 'This image {} has more than one face!'.format(self.image_path)})
            return
        for face_local_ in face_local:
            #print("aaa")
            shape = self.shape_predictor(image, face_local_.rect)
        feature = self.face_rec_model.compute_face_descriptor(image, shape)
        feature = [str(item) for item in np.asarray(feature).tolist()]
        feature = ','.join(feature)
        command = f'insert into face_feature (name, feature) value(\'{name}\', \'{feature}\')'
        self.mysql.execute_command(f'delete from face_feature where name = \'{name}\';')
        self.mysql.execute_command(command)
        print("[INFO]: Insert succeed!")

        self.mysql.close()
        self.write({'status': 'Finished',
                        'message': 'Finished insert face!'})


