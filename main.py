import multiprocessing as mp
import requests
#import threading

from Server.videoProcessServer.cutServer import start_web_server
from tools.utlis import load_json, convert_2_json

def main():
    start_web_server()

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()
