Prep:

- `wget -P ./filter https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
- `wget -P ./filter https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx`
- `hf download lmstudio-community/Phi-3.1-mini-4k-instruct-GGUF Phi-3.1-mini-4k-instruct-Q4_K_M.gguf --local-dir ./filter`

Run:

1. `mediamtx`
2. `uv run filter/main.py`
3. `ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -c:v libx264 -preset ultrafast -tune zerolatency -loglevel warning -f flv rtmp://127.0.0.1:1935/live/stream`
    - or `ffmpeg -re -stream_loop -1 -i consent1.flv -vf "scale=1280:720,fps=30" -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -profile:v baseline -c:a aac -ar 44100 -b:a 128k -f flv rtmp://127.0.0.1:1935/live/stream`
4. `ffplay -loglevel error rtsp://127.0.0.1:8554/filtered`
