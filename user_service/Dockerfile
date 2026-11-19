FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY user_service/ .
EXPOSE 5001 50051
CMD ["python", "app.py"]