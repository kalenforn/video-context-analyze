FROM nvidia/cuda:nvidia/cuda:10.0-cudnn7-runtime-ubi7

RUN apt update
  && apt install python3 ffmpeg vim cmake git make gcc g++ python3-pip libgl1-mesa-glx
  && mkdir /App
  && cd /App
  && git clone https://github.com/davisking/dlib.git
  && cd dlib/
  && mkdir build/
  && cd build/
  && cmake .. -DDLIB_USE_CUDA=1 -DUSE_AVX_INSTRUCTIONS=1
  && make -j4
  && make install
  && apt install python3-setuptools
  && cd ..
  && python3 setup.py install --set DLIB_USE_CUDA=1 --set USE_AVX_INSTRUCTIONS=1