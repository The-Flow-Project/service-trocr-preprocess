# service-trocr-preprocess

microservice to preprocess trocr training material with xml files

## Installation

```bash
# Installation of the service
python3 -m venv fastapi
source fastapi/bin/activate

pip install -r requirements.txt

# Start the service in the background
export API_KEY=your_api_key_here
export STATUS_FILE=status_json_file.json
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > service-trocr-preprocess.log 2>&1 &
```
