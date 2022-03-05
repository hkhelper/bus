FROM python:3.8-slim-buster
WORKDIR /app

ENV TZ=Asia/Shanghai

RUN apt-get upgrade -y \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN pip3 install pandas requests==2.26.0 PyExecJS==1.5.1 Pillow==8.0.1 httpx==0.19.0

WORKDIR /app
COPY . .
ENV PYTHONUNBUFFERED 1
CMD python3 docker_hksz.py