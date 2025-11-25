import urllib.request
import os

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

def download_file(url, filename):
    if os.path.exists(filename):
        print(f"{filename} already exists")
        return
    
    print(f"Downloading {filename}...")
    urllib.request.urlretrieve(url, filename)
    print("Done!")

if __name__ == "__main__":
    download_file(MODEL_URL, "kokoro-v1.0.onnx")
    download_file(VOICES_URL, "voices-v1.0.bin")
