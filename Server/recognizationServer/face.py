import os
import cv2
import dlib
import datetime
import face_recognition

import numpy as np

from tools.log import write_log
from Server.recognizationServer.base import BaseRecognition, total_time

LOG_DIR = os.path.join('log', 'fr')
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)

class FaceDetecter(BaseRecognition):

    def __init__(self, key_name, face_feature, threshold):
        """
        Init.
        """
        super(FaceDetecter, self).__init__('', 'dlib', port=9998)
        currentpath = os.path.dirname(os.path.abspath(__file__))
        self.detector = dlib.cnn_face_detection_model_v1(
            currentpath + '/models/mmod_human_face_detector.dat')
        self.face_rec_model = dlib.face_recognition_model_v1(currentpath + '/models/face_model.dat')
        self.shape_predictor = dlib.shape_predictor(currentpath + '/models/face_alignment.dat')
        self.cascade = cv2.CascadeClassifier(currentpath + "/models/haarcascade_frontalface_alt.xml")
        message = "[INFO]: {} Fr model loaded!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        self.key_name = key_name
        self.face_feature = face_feature
        self.face_feature.insert(0, [0] * 128)
        self.threshold = threshold

    def get_image_feature(self, img):
        """
        This is a factor function which are used to produce a image's face feature.
        Input a image's path or a np.ndarray, output this image's face feature.

        <-- Notice! -->
        ####  If this use to get the key face feature,
        ####  weather the input is str or np.ndarray data,
        ####  each image only include one face.

        ##### If this use to get the frame's face feature,
        ##### 2 or more face can in image.
        <-- End! -->

        :param img: file path or image data.
        :return: if there has a face ,return it's feature, else return None.
        """
        message = "[INFO]: {} Get face feature!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        img_point = self.image_process(img)
        return self.extract_feature(img, img_point)

    def image_process(self, image):
        """
        Process one image.(B, G, R)
        Input a image's path or a np.ndarray, output this image's face feature.
        Select output image's format by self.schema.
        :param image: file path or image data(3 dimension).
        :return: a face picture(224, 224, 3).
        """
        message = "[INFO]: {} Image process!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        if isinstance(image, str):
            image = cv2.imread(image)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        b, g, r = cv2.split(image)
        image = cv2.merge([r, g, b])
        face_image = self.detector(image, 1)

        return face_image

    def extract_feature(self, image, img_point) -> np.ndarray:
        """
        Input a processed data, output this image's face feature.
        :param image: processed image data.
        :return: if there has a face ,return it's feature, else return None.
        """
        message = "[INFO]: {} Extract feature!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        if image is None:
            return None
        face_feature = []
        for index, face in enumerate(img_point):
            shape = self.shape_predictor(image, face.rect)
            face_feature.append(self.face_rec_model.compute_face_descriptor(image, shape))
        face_feature = np.asarray(face_feature)

        return face_feature

    def inference(self, frame_feature) -> list:
        """
        Inference the person.
        :param frame_feature: predict face feature.
        :return: name list.
        """
        message = "[INFO]: {} Inference face feature!".format(str(datetime.datetime.now()).split('.')[0])
        write_log(message=message, file_=os.path.join(LOG_DIR, 'run.log'))
        compare_result = np.zeros(shape=(len(frame_feature), len(self.key_name) + 1))
        for i, feature in enumerate(frame_feature):
            compare_result[i] = face_recognition.face_distance(self.face_feature, feature)
        compare_result = np.where(compare_result < self.threshold, compare_result, 0)
        result = []
        for item in compare_result:
            if np.argmax(item) <= 0 :
                continue
            result.append(self.key_name[np.argmax(item) - 1])
        return result

    # @total_time
    def _recognize(self, image: list) -> str:
        """
        starting recognize, send a message to the judge process.
        :param _input: video frame.
        :return: name list.
        """
        assert not isinstance(image, list), "[ERROR]:Recognized object must be np.ndarray, " \
                                                   "but give a {} type value!".format(type(image))
        result = []
        #image = cv2.resize
        frame_feature = self.get_image_feature(image)
        if len(frame_feature) > 0:
            result = self.inference(frame_feature)
            result = ','.join(result) if len(result) > 0 else ''
        if len(result) == 0:
            return ''
        return result

    @staticmethod
    def _server_start_print(self):
        print("[INFO]:Start face recognization Server web server.")
