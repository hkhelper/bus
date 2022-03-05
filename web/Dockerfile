FROM python:3.8-slim-buster
WORKDIR /app

RUN apt-get update \
    && apt-get -y install default-libmysqlclient-dev build-essential \
    && pip3 install -i https://pypi.douban.com/simple/ -U pip \
    && pip3 config set global.index-url https://pypi.douban.com/simple/ \
    && pip3 install pandas==1.3.3 requests==2.26.0 Django==3.2.8 mysqlclient django-import-export==2.5.0 djangorestframework==3.12.4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
ENV PYTHONUNBUFFERED 1

CMD python3