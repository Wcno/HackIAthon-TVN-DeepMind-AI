import json, os, sys
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
import numpy as np, onnxruntime as ort
ort.preload_dlls()
from embedders import load
desc = json.load(open("topic_descriptions.json"))
labels = [t for t, texts in desc.items() for _ in texts]; texts = [x for v in desc.values() for x in v]
os.makedirs("dvectors", exist_ok=True)
for key in sys.argv[1:]:
    e = load(key, gpu=True)
    np.save(f"dvectors/{key}.npy", e(texts, True))
json.dump(labels, open("dvectors/labels.json", "w"))
