# Train "hey bolt" for openWakeWord, in ONE Colab cell. Python 3.12 runtime + T4 GPU.
# Every fix from today is built in. Safe to re-run: finished parts are skipped.
import os, sys, subprocess, collections, shutil

WAKE_WORD = "hey bolt"
os.chdir("/content")

def run(cmd, show=True):
    """Run a shell command, show its output as it goes, and stop with the error if it fails."""
    print(f"\n### {cmd[:120]}", flush=True)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = collections.deque(maxlen=40)
    for line in p.stdout:
        tail.append(line)
        if show:
            print(line.rstrip()[-200:], flush=True)
    if p.wait() != 0:
        print("".join(tail))
        raise SystemExit(f"FAILED (exit {p.returncode}): {cmd[:120]}")

# ---- 0. Checks
v = sys.version_info
assert v[:2] == (3, 12), f"Python {v.major}.{v.minor}: pick an older Runtime version (needs 3.12)"
run("nvidia-smi -L")  # fails here if the GPU isn't switched on (Runtime -> Change runtime type -> T4 GPU)

# ---- 1. Google Drive, so the finished model survives if Colab disconnects
from google.colab import drive
drive.mount("/content/drive")
SAVE_TO = "/content/drive/MyDrive/bolt_wake_word"
os.makedirs(SAVE_TO, exist_ok=True)

# ---- 2. Software, with today's fixes
run("pip install -q torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu126", show=False)
if not os.path.exists("piper-sample-generator"):
    run("git clone -q https://github.com/rhasspy/piper-sample-generator")
if not os.path.exists("piper-sample-generator/models/en_US-libritts_r-medium.pt"):
    run("wget -q -O piper-sample-generator/models/en_US-libritts_r-medium.pt "
        "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt")
if not os.path.exists("openwakeword"):
    run("git clone -q https://github.com/dscripka/openwakeword")
run("pip install -q -e ./openwakeword", show=False)
run("pip install -q piper-phonemize-cross webrtcvad mutagen==1.47.0 torchinfo==1.8.0 torchmetrics==1.2.0 "
    "speechbrain==0.5.14 audiomentations==0.33.0 torch-audiomentations==0.11.2 acoustics==0.2.6 "
    "pronouncing==0.2.0 datasets==2.14.6 deep-phonemizer==0.0.19 onnx==1.17.0 'protobuf>=5.26,<6'", show=False)
models = "openwakeword/openwakeword/resources/models"
os.makedirs(models, exist_ok=True)
for name in ("embedding_model.onnx", "embedding_model.tflite", "melspectrogram.onnx", "melspectrogram.tflite"):
    if not os.path.exists(f"{models}/{name}"):
        run(f"wget -q -O {models}/{name} https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/{name}")

# ---- 3. Background sounds and room echoes (same as the notebook, run in a fresh Python)
PREP = r'''
import os, numpy as np, scipy.io.wavfile, datasets
from pathlib import Path
from tqdm import tqdm
def save(folder, name, audio):
    scipy.io.wavfile.write(os.path.join(folder, name), 16000, (audio * 32767).astype(np.int16))
if not os.path.exists("mit_rirs/.done"):
    os.makedirs("mit_rirs", exist_ok=True)
    for row in tqdm(datasets.load_dataset("davidscripka/MIT_environmental_impulse_responses", split="train", streaming=True)):
        save("mit_rirs", row["audio"]["path"].split("/")[-1], row["audio"]["array"])
    open("mit_rirs/.done", "w").close()
if not os.path.exists("audioset_16k/.done"):
    os.makedirs("audioset_16k", exist_ok=True)
    ds = datasets.Dataset.from_dict({"audio": [str(i) for i in Path("audioset/audio").glob("**/*.flac")]})
    for row in tqdm(ds.cast_column("audio", datasets.Audio(sampling_rate=16000))):
        save("audioset_16k", row["audio"]["path"].split("/")[-1].replace(".flac", ".wav"), row["audio"]["array"])
    open("audioset_16k/.done", "w").close()
if not os.path.exists("fma/.done"):
    os.makedirs("fma", exist_ok=True)
    fma = iter(datasets.load_dataset("rudraml/fma", name="small", split="train", streaming=True)
               .cast_column("audio", datasets.Audio(sampling_rate=16000)))
    for i in tqdm(range(3600 // 30)):  # one hour of 30-second music clips
        row = next(fma)
        save("fma", row["audio"]["path"].split("/")[-1].replace(".mp3", ".wav"), row["audio"]["array"])
    open("fma/.done", "w").close()
print("background audio ready")
'''
open("prep.py", "w").write(PREP)
if not os.path.exists("audioset/audio"):
    os.makedirs("audioset", exist_ok=True)
    run("wget -q -O audioset/bal_train09.tar https://huggingface.co/datasets/agkphysics/AudioSet/resolve/main/data/bal_train09.tar")
    run("cd audioset && tar -xf bal_train09.tar")
run(f"{sys.executable} prep.py")

# ---- 4. The big pre-made "not the wake word" sounds (several GB; -c resumes a broken download)
base = "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main"
run(f"wget -q -c {base}/openwakeword_features_ACAV100M_2000_hrs_16bit.npy")
run(f"wget -q -c {base}/validation_set_features.npy")

# ---- 5. Training settings
import yaml
config = yaml.safe_load(open("openwakeword/examples/custom_model.yml"))
config["target_phrase"] = [WAKE_WORD]
config["model_name"] = WAKE_WORD.replace(" ", "_")
config["n_samples"] = 1000
config["n_samples_val"] = 1000
config["steps"] = 10000
config["target_accuracy"] = 0.6
config["target_recall"] = 0.25
config["background_paths"] = ["./audioset_16k", "./fma"]
config["background_paths_duplication_rate"] = [1, 1]
config["false_positive_validation_data_path"] = "validation_set_features.npy"
config["feature_data_files"] = {"ACAV100M_sample": "openwakeword_features_ACAV100M_2000_hrs_16bit.npy"}
config["piper_sample_generator_path"] = "./piper-sample-generator"
yaml.dump(config, open("my_model.yaml", "w"))

# ---- 6. Train: make the clips, add noise and echo, then train
for flag in ("--generate_clips", "--augment_clips", "--train_model"):
    run(f"{sys.executable} openwakeword/openwakeword/train.py --training_config my_model.yaml {flag}")

# ---- 7. Save it to Google Drive and download it
model = f"{config['output_dir']}/{config['model_name']}.onnx"
shutil.copy(model, SAVE_TO)
print(f"\nDONE! {model} ({os.path.getsize(model) // 1024} KB), also saved to Google Drive: {SAVE_TO}")
from google.colab import files
files.download(model)
