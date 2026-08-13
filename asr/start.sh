#!/usr/bin/env bash
set -euo pipefail

FUNASR_PORT="${FUNASR_PORT:-10095}"
ASR_PORT="${PORT:-${ASR_PORT:-8080}}"
FUNASR_MODEL_DIR="${FUNASR_MODEL_DIR:-/workspace/models}"
FUNASR_DECODER_THREADS="${FUNASR_DECODER_THREADS:-3}"
FUNASR_IO_THREADS="${FUNASR_IO_THREADS:-1}"
FUNASR_MODEL_THREADS="${FUNASR_MODEL_THREADS:-1}"
HOTWORD_FILE="${HOTWORD_FILE:-${FUNASR_MODEL_DIR}/hotwords.txt}"

mkdir -p "${FUNASR_MODEL_DIR}"
touch "${HOTWORD_FILE}"

if [[ -n "${FUNASR_RUNTIME_DIR:-}" && -f "${FUNASR_RUNTIME_DIR}/run_server_2pass.sh" ]]; then
  RUNTIME_DIR="${FUNASR_RUNTIME_DIR}"
else
  RUNTIME_SCRIPT="$(find /workspace -path '*/runtime/run_server_2pass.sh' -print -quit)"
  RUNTIME_DIR="${RUNTIME_SCRIPT%/*}"
fi

if [[ -z "${RUNTIME_DIR}" || ! -f "${RUNTIME_DIR}/run_server_2pass.sh" ]]; then
  echo "Cannot find FunASR runtime/run_server_2pass.sh under /workspace."
  exit 1
fi

echo "Starting FunASR 2-pass runtime on 127.0.0.1:${FUNASR_PORT}"
echo "Resource cap: decoder=${FUNASR_DECODER_THREADS}, io=${FUNASR_IO_THREADS}, model=${FUNASR_MODEL_THREADS}, OMP=${OMP_NUM_THREADS:-1}"
cd "${RUNTIME_DIR}"
bash run_server_2pass.sh \
  --download-model-dir "${FUNASR_MODEL_DIR}" \
  --vad-dir damo/speech_fsmn_vad_zh-cn-16k-common-onnx \
  --model-dir damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-onnx \
  --online-model-dir damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online-onnx \
  --punc-dir damo/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727-onnx \
  --itn-dir thuduj12/fst_itn_zh \
  --hotword "${HOTWORD_FILE}" \
  --port "${FUNASR_PORT}" \
  --decoder-thread-num "${FUNASR_DECODER_THREADS}" \
  --io-thread-num "${FUNASR_IO_THREADS}" \
  --model-thread-num "${FUNASR_MODEL_THREADS}" \
  --certfile 0 > /workspace/peach-asr/funasr.log 2>&1 &

export FUNASR_TARGET="${FUNASR_TARGET:-ws://127.0.0.1:${FUNASR_PORT}}"
export ASR_PORT
cd /workspace/peach-asr
exec python3 -m uvicorn gateway:app --host 0.0.0.0 --port "${ASR_PORT}"
