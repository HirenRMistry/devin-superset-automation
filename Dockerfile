FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dispatcher/ dispatcher/
COPY scanner/ scanner/
COPY static/ static/

ENV PYTHONUNBUFFERED=1
VOLUME /data

EXPOSE 8000
CMD ["uvicorn", "dispatcher.main:app", "--host", "0.0.0.0", "--port", "8000"]
