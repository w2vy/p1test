FROM alpine:3.15

RUN mkdir /home/p1test
WORKDIR /home/p1test

# Python
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools
RUN apk add gcc g++ make libffi-dev openssl-dev git
RUN pip3 install pycryptodome
RUN pip3 install requests

# Copy our scripts
COPY entrypoint.sh ./
COPY p1_node.py ./
CMD ["/home/p1test/entrypoint.sh"]
