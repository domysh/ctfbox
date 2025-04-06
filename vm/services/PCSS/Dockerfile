FROM python:3.6-slim

RUN apt-get update && apt-get install -y socat gcc g++ make libffi-dev libssl-dev
WORKDIR /service/
COPY ./requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
ADD ./main.py ./main.py
RUN chmod +x main.py
ENTRYPOINT socat -d TCP-LISTEN:3000,reuseaddr,fork EXEC:'timeout -k 5 30 python3 -u main.py'