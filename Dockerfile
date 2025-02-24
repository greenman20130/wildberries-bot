FROM python:3.10 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.10

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY ./app /app

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]