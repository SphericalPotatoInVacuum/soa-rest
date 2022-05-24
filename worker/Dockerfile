FROM python:3.9.12

WORKDIR /worker
RUN mkdir user_pics

RUN apt update && apt install -y wkhtmltopdf

COPY worker/requirements.txt ./
RUN pip3 install -r requirements.txt

COPY worker ./

ENTRYPOINT bash -c "while ! curl -s rabbitmq:15672 > /dev/null; do echo waiting for rabbitmq; sleep 3; done; python3 worker.py"
