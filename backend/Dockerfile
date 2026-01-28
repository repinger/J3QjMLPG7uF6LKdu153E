FROM python:alpine

WORKDIR /app

COPY * .
RUN pip install --no-cache-dir -r requirements.txt \
	&& mkdir /db

EXPOSE 5000

CMD [ "python", "app.py" ]
