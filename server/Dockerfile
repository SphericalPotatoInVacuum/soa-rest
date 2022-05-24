FROM python:3.9.12

WORKDIR /server
RUN mkdir user_pics

COPY server/requirements.txt ./
RUN pip3 install -r requirements.txt

COPY server ./

ENTRYPOINT bash -c "while ! curl -s rabbitmq:15672 > /dev/null; do echo waiting for rabbitmq; sleep 3; done; python3 run.py"
