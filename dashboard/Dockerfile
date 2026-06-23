FROM python:3.12-slim
WORKDIR /app
RUN pip install flask google-cloud-bigquery pandas db-dtypes
COPY app.py .
ENV PORT=8080
CMD ["python3", "app.py"]
