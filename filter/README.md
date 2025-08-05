Prep:

- `wget https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx`

Run:

1. `mediamtx`
2. `uv run main.py`
3. `ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -c:v libx264 -preset ultrafast -tune zerolatency -loglevel warning -f flv rtmp://127.0.0.1:1935/live/stream`
4. `ffplay -loglevel error rtsp://127.0.0.1:8554/blurred`
