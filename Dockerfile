FROM python:3.12-slim

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get -y install python3-opencv
RUN apt-get -y install git
# Set working dir
WORKDIR /app
ENV PYTHONPATH=/app

# Copy app
COPY ./app /app

# Install dependencies
RUN python -m pip install --upgrade pip
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]