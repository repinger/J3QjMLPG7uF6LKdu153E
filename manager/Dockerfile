FROM python:alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
	&& mkdir -p /db

COPY . .

CMD ["python", "app.py"]
