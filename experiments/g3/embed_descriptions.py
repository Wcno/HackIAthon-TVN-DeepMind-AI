"""Embed the topic descriptions with each given model on the NVIDIA GPU.

    <gpu-venv>/bin/python experiments/g3/embed_descriptions.py <model>...

GPU only: needs a venv with onnxruntime-gpu (see README). Writes `dvectors/<model>.npy` and `dvectors/labels.json`.
"""
import json, os, sys
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
import numpy as np, onnxruntime as ort
ort.preload_dlls()
from corpus import DATA, HERE
from embedders import load
desc = json.load((DATA / "topic_descriptions.json").open())
labels = [t for t, texts in desc.items() for _ in texts]; texts = [x for v in desc.values() for x in v]
(HERE / "dvectors").mkdir(exist_ok=True)
for key in sys.argv[1:]:
    e = load(key, gpu=True)
    np.save(HERE / "dvectors" / f"{key}.npy", e(texts, True))
json.dump(labels, (HERE / "dvectors" / "labels.json").open("w"))
