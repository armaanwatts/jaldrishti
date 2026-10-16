FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEPLOYMENT_MODE=cloud
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY frontend/dist /app/frontend/dist
COPY cloud_start.py /app/cloud_start.py
CMD ["python", "cloud_start.py"]
