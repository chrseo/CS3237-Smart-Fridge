import time
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
import numpy as np
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized, TracedModel

import paho.mqtt.client as mqtt
import cv2
import os
import time
from collections import defaultdict

import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
import json

import io
import base64

from datetime import datetime

def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.subscribe("fridge/photo")

def on_message(client, userdata, msg):
    if msg.payload:  # take photos every ?s until door is closed
        # Take picture using camera, then run YOLO model and save counts to database
        image = json.loads(msg.payload)
        cv2.imwrite('test.jpg', np.array(image))
        print(f"Photo received!\nSize: {(len(image), len(image[0]), len(image[0][0]))}")

        with torch.no_grad():
            results = detect(image)
        if (firebase_data):
            b_threshold = db.collection(str('predict')).document(str('banana')).get().to_dict()['predicted_data']
            a_threshold = db.collection(str('predict')).document(str('apple')).get().to_dict()['predicted_data']
            e_threshold = db.collection(str('predict')).document(str('orange')).get().to_dict()['predicted_data']
            thresholds = {'banana':sum(b_threshold), 'apple':sum(a_threshold), 'orange':sum(e_threshold)}
        else:
            b_threshold = db.collection(str('predict_demo')).document(str('banana')).get().to_dict()['predicted_data']
            a_threshold = db.collection(str('predict_demo')).document(str('apple')).get().to_dict()['predicted_data']
            e_threshold = db.collection(str('predict_demo')).document(str('orange')).get().to_dict()['predicted_data']
            thresholds = {'banana': sum(b_threshold), 'apple': sum(a_threshold), 'orange': sum(e_threshold)}
        sensor_val = ""
        firestore_payload = {}
        for item in FRIDGE_ITEMS:
            count = results[item] if item in results else 0
            firestore_payload[item] = int(count)
        no_stock = 0
        items_below_threshold = []
        for t in (thresholds):
            if firestore_payload[t] < thresholds[t]:
                no_stock += 1
                # items_below_threshold.append(ITEM_COLOURS[t])
                
        if no_stock == len(thresholds):
            sensor_val = "r"
        elif no_stock > 0:
            sensor_val = "y"
        else:
            sensor_val = "g"

        '''
        NOTE: We are making doc titles date format so that new count updates
        within the same day updates the same doc.

        Having just 1 end of the day count so we can avoid group-bys etc.
        '''
        current_date = datetime.now().strftime("%Y%m%d")
        firestore_payload['timestamp'] = current_date # or make this a value that firestore understands so we can query timeframes
    
        # that way we can use prev doc to use for count
        # when we generate fake data, generate to yesterdays date
        # also when there is no data for that day, copy over previous count for that day

        stocks_ref = db.collection('stocks').document(current_date)

        # calculate consumption currently
        consumption = db.collection('consumption').document(current_date).get()
        if consumption.exists and stocks_ref.get().exists:
            s = stocks_ref.get().to_dict()

            # previous stock count - current stock count
            curr_c = {
                'apple': s['apple'] - firestore_payload['apple'],
                'banana': s['banana'] - firestore_payload['banana'],
                'orange': s['orange'] - firestore_payload['orange'],
            }

            c = consumption.to_dict()

            print('updating consumption in firebase...')
            print(f"consumed {curr_c['apple']} apples")
            print(f"consumed {curr_c['banana']} bananas")
            print(f"consumed {curr_c['orange']} oranges")
            
            # only add to today's total consumption if the consumption was positive
            c['apple'] += curr_c['apple'] if curr_c['apple'] > 0 else 0
            c['banana'] += curr_c['banana'] if curr_c['banana'] > 0 else 0
            c['orange'] += curr_c['orange'] if curr_c['orange'] > 0 else 0
            c['timestamp'] = current_date

            # update the consumption!
            c_ref = db.collection('consumption').document(current_date)
            c_ref.set(c)
        elif stocks_ref.get().exists:
            s = stocks_ref.get().to_dict()

            # previous stock count - current stock count
            c1, c2, c3 = s['apple'] - firestore_payload['apple'], s['banana'] - firestore_payload['banana'], s['orange'] - firestore_payload['orange']
            # only put consumption if it was positive
            curr_c = {
                'apple': c1 if c1 > 0 else 0,
                'banana': c2 if c2 > 0 else 0,
                'orange': c3 if c3 > 0 else 0,
                'timestamp': current_date,
            }

            # update the consumption!
            c_ref = db.collection('consumption').document(current_date)
            c_ref.set(curr_c)
        else: # no current stock count, this is the first run and we can just pass.
            pass

        # -- UPDATE CURRENT STOCK TO FIREBASE -- #

        # save image alongside everything
        my_base64_jpgData = None
        with open("test.jpg", "rb") as image_file:
            my_base64_jpgData = base64.b64encode(image_file.read())
        firestore_payload['img_base64'] = "" if not my_base64_jpgData else my_base64_jpgData.decode('ascii')

        stocks_ref.set(firestore_payload)

        print(sensor_val)
        # pub to stock thread
        client.publish("fridge/stock", sensor_val)
    else:
        print("Fridge door is closed.")


def detect(save_img=False,
           agnostic_nms=False,
           augment=False,
           classes=None,
           conf_thres=0.25,
           device='cpu',
           exist_ok=False,
           imgsz=640,
           iou_thres=0.45,
           name='exp',
           trace=False,
           nosave=True,
           project='yolov7/runs/detect',
           save_conf=False,
           save_txt=False,
           source='test.jpg',
           update=False,
           view_img=False,
           weights='yolov7/yolov7.pt'):

    # Directories
    save_dir = Path(increment_path(Path(project) / name, exist_ok=exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size

    if trace:
        model = TracedModel(model, device, imgsz)

    if half:
        model.half()  # to FP16

    # Second-stage classifier
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    old_img_w = old_img_h = imgsz
    old_img_b = 1

    t0 = time.time()
    for path, img, im0s, vid_cap in dataset:
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Warmup
        if device.type != 'cpu' and (old_img_b != img.shape[0] or old_img_h != img.shape[2] or old_img_w != img.shape[3]):
            old_img_b = img.shape[0]
            old_img_h = img.shape[2]
            old_img_w = img.shape[3]
            for i in range(3):
                model(img, augment=augment)[0]

        # Inference
        t1 = time_synchronized()
        with torch.no_grad():   # Calculating gradients would cause a GPU memory leak
            pred = model(img, augment=augment)[0]
        t2 = time_synchronized()

        # Apply NMS
        pred = non_max_suppression(pred, conf_thres, iou_thres, classes=classes, agnostic=agnostic_nms)
        t3 = time_synchronized()

        # Apply Classifier
        if classify:
            pred = apply_classifier(pred, modelc, img, im0s)

        # Process detections
        for i, det in enumerate(pred):  # detections per image
            p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # img.jpg
            txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh

            results = {}

            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string
                    results[names[int(c)]] = n

            print(f'{s}Done. ({(1E3 * (t2 - t1)):.1f}ms) Inference, ({(1E3 * (t3 - t2)):.1f}ms) NMS')
            return results


cred = credentials.Certificate('cs3237-fridge-firebase-adminsdk-d14fo-88295eb35b.json')
app = firebase_admin.initialize_app(cred)
db = firestore.client()

FRIDGE_ITEMS = ['banana', 'apple', 'orange']
ITEM_COLOURS = {'banana':'y', 'apple':'b', 'orange':'w'}
firebase_data = True

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("Connecting")
client.connect("192.168.199.37", 1883, 60)
client.loop_forever()

