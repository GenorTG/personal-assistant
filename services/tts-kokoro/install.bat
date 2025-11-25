@echo off
echo Creating virtual environment for Kokoro TTS...
python -m venv .venv
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo Downloading model files...
python download_models.py

echo Installation complete!
pause
