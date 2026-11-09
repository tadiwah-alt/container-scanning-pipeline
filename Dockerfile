FROM python:3.11.17-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --upgrade --no-cache-dir setuptools wheel

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*


RUN useradd --create-home appuser


USER appuser

COPY . .

EXPOSE 5000

CMD ["python", "app/app.py"]