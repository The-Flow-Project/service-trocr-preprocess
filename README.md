# service-trocr-preprocess
microservice to preprocess trocr training material with xml files

## Installation

```bash
# Installation of mongodb (needs Docker installed, check if sudo is needed)
docker run --name mongodb \
    -p 127.0.0.1:27017:27017 \
    -e MONGO_INITDB_ROOT_USERNAME=your_username \
    -e MONGO_INITDB_ROOT_PASSWORD=your_password \
    -d mongo
sudo ufw allow from 127.0.0.1 to any port 27017
sudo ufw deny 27017

# Installation of the service
python3 -m venv fastapi
source fastapi/bin/activate

pip install -r requirements.txt

# Start the service in the background
export MONGO_USERNAME=your_username
export MONGO_PASSWORD=your_password
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > service-trocr-preprocess.log 2>&1 &
```
