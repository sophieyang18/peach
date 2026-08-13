# Peach ASR / FunASR 2-pass Streaming

`peach-asr` is an independent WebSocket ASR service for immersive interviews. It wraps the official FunASR CPU Runtime 2-pass server and exposes:

- `GET /health`
- `GET /health/deep`
- `WS /asr`

The service is intentionally separated from `peach-api` because ASR keeps models resident in memory and uses long WebSocket connections.

## 4 vCPU / 8GB Profile

Defaults are tuned for a 4 vCPU / 8GB CloudBase Run service:

```bash
FUNASR_DECODER_THREADS=3
FUNASR_IO_THREADS=1
FUNASR_MODEL_THREADS=1
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
```

Keep minimum instances at `1` in production to avoid model cold start during interviews.

## Local Run

```bash
docker compose up --build asr
```

Then set the frontend ASR URL:

```bash
LOCAL_ASR_WS_URL=ws://127.0.0.1:10096/asr ./start-dev.sh --restart
```

The frontend will prefer FunASR and fall back to browser Web Speech if `/asr` is unavailable.

## CloudBase Run

Deploy this directory with `asr/Dockerfile`, service port `8080`, and allocate at least `4 vCPU / 8GB`.

Frontend build variable:

```bash
VITE_ASR_WS_URL=wss://<your-peach-asr-domain>/asr
```
