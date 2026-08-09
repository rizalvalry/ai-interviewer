FROM python:3.11-slim

# Non-root user required by Hugging Face Docker Spaces (uid 1000).
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

# Install deps as root (writes to system site-packages), then hand the tree to the app user.
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# faster-whisper/ctranslate2 downloads the Whisper model on first run (WhisperModel(...) in
# asr.py). HF_HOME must point at a directory the non-root user owns, or the download fails
# under the platform's read-only-filesystem assumptions.
ENV HF_HOME=/home/user/.cache/huggingface
RUN mkdir -p $HF_HOME && chown -R user:user /home/user

COPY --chown=user:user . .

USER user

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
