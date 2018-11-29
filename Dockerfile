FROM python:2.7
COPY requirements.txt requirements_test.txt /
RUN pip install -r /requirements.txt
RUN pip install -r /requirements_test.txt
COPY . /app
WORKDIR /app
CMD python setup.py test
