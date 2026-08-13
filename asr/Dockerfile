FROM registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13

ENV PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    FUNASR_PORT=10095 \
    ASR_PORT=8080 \
    FUNASR_DECODER_THREADS=3 \
    FUNASR_IO_THREADS=1 \
    FUNASR_MODEL_THREADS=1 \
    FUNASR_MODEL_DIR=/workspace/models

WORKDIR /workspace/peach-asr

RUN python3 -m pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.32.1" websockets==14.1

COPY asr/gateway.py /workspace/peach-asr/gateway.py
COPY asr/start.sh /workspace/peach-asr/start.sh
COPY asr/hotwords.txt /workspace/models/hotwords.txt

RUN chmod +x /workspace/peach-asr/start.sh

EXPOSE 8080

CMD ["/workspace/peach-asr/start.sh"]
