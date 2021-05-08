# !/bin/bash
# 请读者自行修改部分内容！
docker run -d --network bridge --name media-server -p 1935:1935 -p 8500:8500 -v PATH/TO/YOUR/video/:/usr/src/app/video -v PATH/TO/CODE/Node-Media-Server/app.js:/usr/src/app/app.js -v PATH/TO/CODE/Node-Media-server/node_relay_server.js:/usr/src/app/node_relay_server.js -v PATH/TO/CODE/Node-Media-server/privatekey.pem:/privatekey.pem -v PATH/TO/CODE/Node-Media-server/certificate.pem:/certificate.pem illuspas/node-media-server:latest
