FROM python:2.7

RUN apt-get update && apt-get -y install gettext-base \
     && apt-get clean && rm -rf /var/lib/apt/lists/*
     
COPY requirements.txt requirements_test.txt /
RUN pip install -r /requirements.txt
RUN pip install -r /requirements_test.txt
COPY . /app
WORKDIR /app
CMD python setup.py test
