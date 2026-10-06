FROM python:3.11-slim
WORKDIR /workspace
COPY backend/requirements*.txt /workspace/backend/
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /workspace/backend/requirements.txt -r /workspace/backend/requirements-documents.txt
COPY backend /workspace/backend
COPY scripts /workspace/scripts
COPY ml /workspace/ml
COPY data /workspace/data
ENV PYTHONPATH=/workspace/backend:/workspace HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "backend/run.py"]
