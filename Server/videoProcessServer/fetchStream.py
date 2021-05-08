import os
import cv2
import m3u8
import time
import threading

from requests import get

# 用于下载直播
class FetchStream:

    def __init__(self, url, root_dir):

        self.url = url
        self.save_dir = os.path.join(root_dir, 'fetch')
        if not os.path.exists(self.save_dir):
            os.mkdir(self.save_dir)
            print("[INFO]:New dir")
        self.save_file = []
        self.count = 0

    def download_file(self):

        while True:
            dynamicplaylist = m3u8.load(self.url)
            for videosegment in dynamicplaylist.segments:
                videouri = videosegment.absolute_uri
                videofname = videosegment.uri.split('/')[-1]
                try:
                    out_name = os.path.join(self.save_dir, str(self.count) + videofname)
                    with open(out_name, "wb") as file:
                        response = get(videouri)
                        file.write(response.content)
                        file.close()
                    self.count += 1
                    self.save_file.append(out_name)
                except Exception as e:
                    print(e)
                    break

    def start_download(self):
        target = threading.Thread(target=self.download_file)
        target.start()
        print("[INFO]:start threading")

    def change_file(self):
        return self.succeed()

    def wait(self):

        while len(self.save_file) < 1:
            time.sleep(1)
            print("[INFO]:Waiting")

    def succeed(self):
        self.wait()
        video_path = self.save_file.pop()
        flag = True
        while flag:
            # 判断下载的文件是否可读
            cap = cv2.VideoCapture(video_path)
            _, frame = cap.read()
            if _:
                flag = False
            else:
                self.wait()
                video_path = self.save_file.pop()
            cap.release()
        return video_path



