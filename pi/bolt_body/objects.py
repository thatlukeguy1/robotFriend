"""
LESSON: Finding THINGS in a picture
===================================
NanoDet (from OpenCV's model zoo, free to use under the Apache 2.0 licence) is a
small "object detector": give it a picture and it says WHAT is in it and WHERE,
as boxes. It knows the 80 kinds of everyday thing in a famous practice set of
photos called COCO: people, cups, phones, laptops, chairs, books, cats...

How it reads a picture, in short:
  1. The picture is LETTERBOXED to 416 x 416 (shrunk to fit, with grey bars), the
     size it was trained on.
  2. It scores every small patch of the picture for each of the 80 kinds of thing,
     and guesses how far each object's edges are from that patch.
  3. Many patches find the same cup, so overlapping boxes are boiled down to the
     best one ("non-maximum suppression", NMS).
  4. The boxes are scaled back to the real picture.

Everything happens on the Pi; nothing leaves it to make the boxes.
"""

from pathlib import Path

import numpy as np

from .faces import MODEL_DIR, ensure_models

MODEL = {"object_detection_nanodet_2022nov.onnx": (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_nanodet/"
    "object_detection_nanodet_2022nov.onnx", "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186")}
SIZE = 416
STRIDES = (8, 16, 32)
REG_MAX = 7
SURE = 0.45            # how sure it must be before a box is shown

THINGS = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus", "train", "truck", "boat", "traffic light",
          "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
          "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
          "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
          "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
          "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "sofa",
          "potted plant", "bed", "dining table", "toilet", "TV", "laptop", "mouse", "remote", "keyboard", "phone",
          "microwave", "oven", "toaster", "sink", "fridge", "book", "clock", "vase", "scissors", "teddy bear",
          "hair drier", "toothbrush"]


class ObjectFinder:
    def __init__(self, folder=None):
        import cv2
        self.cv2 = cv2
        folder = ensure_models(MODEL_DIR, MODEL) if folder is None else Path(folder)
        self.net = cv2.dnn.readNet(str(folder / "object_detection_nanodet_2022nov.onnx"))
        self.mean = np.array([103.53, 116.28, 123.675], dtype=np.float32).reshape(1, 1, 3)
        self.std = np.array([57.375, 57.12, 58.395], dtype=np.float32).reshape(1, 1, 3)
        self.anchors = []
        for stride in STRIDES:
            n = int(SIZE / stride)
            xv, yv = np.meshgrid(np.arange(n) * stride, np.arange(n) * stride)
            self.anchors.append(np.column_stack((xv.flatten() + 0.5 * (stride - 1), yv.flatten() + 0.5 * (stride - 1))))

    def find(self, picture, sure=SURE):
        """[{"label", "score", "box": [x, y, width, height]}] in the picture's own pixels."""
        cv2 = self.cv2
        h, w = picture.shape[:2]
        scale = SIZE / max(h, w)                                   # 1. letterbox to 416 x 416
        nh, nw = round(h * scale), round(w * scale)
        top, left = (SIZE - nh) // 2, (SIZE - nw) // 2
        boxed = np.full((SIZE, SIZE, 3), 114, dtype=np.uint8)
        boxed[top:top + nh, left:left + nw] = cv2.resize(picture, (nw, nh))
        blob = cv2.dnn.blobFromImage((boxed.astype(np.float32) - self.mean) / self.std)
        self.net.setInput(blob)
        outs = self.net.forward(self.net.getUnconnectedOutLayersNames())

        boxes, scores = [], []                                     # 2. every patch's guess
        # its answers come as a "what" (80 scores) and a "where" (32 numbers) list per patch size,
        # biggest list (finest patches) first; sorting by shape keeps us safe from their order
        whats = sorted((o for o in outs if o.shape[-1] == len(THINGS)), key=lambda o: -o.size)
        wheres = sorted((o for o in outs if o.shape[-1] == 4 * (REG_MAX + 1)), key=lambda o: -o.size)
        for stride, cls, reg, anchors in zip(STRIDES, whats, wheres, self.anchors):
            cls, reg = cls.reshape(-1, len(THINGS)), reg.reshape(-1, 4 * (REG_MAX + 1))
            e = np.exp(reg.reshape(-1, REG_MAX + 1))
            dist = ((e / e.sum(axis=1, keepdims=True)) @ np.arange(REG_MAX + 1)).reshape(-1, 4) * stride
            boxes.append(np.column_stack([anchors[:, 0] - dist[:, 0], anchors[:, 1] - dist[:, 1],
                                          anchors[:, 0] + dist[:, 2], anchors[:, 1] + dist[:, 3]]))
            scores.append(cls)
        boxes, scores = np.clip(np.concatenate(boxes), 0, SIZE), np.concatenate(scores)
        kinds, best = scores.argmax(axis=1), scores.max(axis=1)
        wh = boxes.copy()
        wh[:, 2:] -= wh[:, :2]
        keep = cv2.dnn.NMSBoxes(wh.tolist(), best.tolist(), sure, 0.6)   # 3. one box per object

        found = []                                                 # 4. back to the real picture
        for i in np.array(keep).flatten():
            x1, y1, x2, y2 = (boxes[i] - [left, top, left, top]) / scale
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
            if x2 - x1 > 4 and y2 - y1 > 4:
                found.append({"label": THINGS[kinds[i]], "score": round(float(best[i]), 2),
                              "box": [round(float(x1)), round(float(y1)), round(float(x2 - x1)), round(float(y2 - y1))]})
        return sorted(found, key=lambda f: -f["score"])
