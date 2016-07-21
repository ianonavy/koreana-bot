FROM python:2.7
ADD . /code
WORKDIR /code
RUN pip install -e /code
RUN pip install -r dev_requirements.txt
CMD python -m koreana_bot.run
