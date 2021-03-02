# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A demo that runs object detection on camera frames using OpenCV.

TEST_DATA=../models

Run face detection model:
python3 detect.py \
  --model ${TEST_DATA}/mobilenet_ssd_v2_face_quant_postprocess_edgetpu.tflite

Run coco model:
python3 detect.py \
  --model ${TEST_DATA}/mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite \
  --labels ${TEST_DATA}/coco_labels.txt

"""
import argparse
import numpy as np
import cv2
import os

from pycoral.adapters.common import input_size
from pycoral.adapters.detect import get_objects
from pycoral.utils.dataset import read_label_file
from pycoral.utils.edgetpu import make_interpreter
from pycoral.utils.edgetpu import run_inference
from tracker import ObjectTracker

mot_tracker = None


def detectCoralDevBoard():
  try:
    if 'MX8MQ' in open('/sys/firmware/devicetree/base/model').read():
      print('Detected Edge TPU dev board.')
      return True
  except: pass
  return False


def main():
    global mot_tracker
    default_model_dir = '../models'
    default_model = 'mobilenet_ssd_v2_coco_quant_postprocess_edgetpu.tflite'
    default_labels = 'coco_labels.txt'
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', help='.tflite model path',
                        default=os.path.join(default_model_dir,default_model))
    parser.add_argument('--labels', help='label file path',
                        default=os.path.join(default_model_dir, default_labels))
    parser.add_argument('--top_k', type=int, default=3,
                        help='number of categories with highest score to display')
    parser.add_argument('--camera_idx', type=int, help='Index of which video source to use. ', default = 0)
    parser.add_argument('--threshold', type=float, default=0.1,
                        help='classifier score threshold')
    parser.add_argument('--tracker', help='Name of the Object Tracker To be used.',
                        default=None,
                        choices=[None, 'sort'])
    parser.add_argument('--videosrc', help='Directly connected (dev) or Networked (net) video source. ', choices=['dev','net','file'],
                        default='dev')
    parser.add_argument('--display', help='Is a display attached',
                        default='False',
                        choices=['True', 'False'])
    parser.add_argument('--netsrc', help="Networked video source, example format: rtsp://192.168.1.43/mpeg4/media.amp",)
    parser.add_argument('--filesrc', help="Video file source. The videos subdirectory gets mapped into the Docker container, so place your files there.",)
    
    args = parser.parse_args()
    
    trackerName=args.tracker
    ''' Check for the object tracker.'''
    if trackerName != None:
        if trackerName == 'mediapipe':
            if detectCoralDevBoard():
                objectOfTracker = ObjectTracker('mediapipe')
            else:
                print("Tracker MediaPipe is only available on the Dev Board. Keeping the tracker as None")
                trackerName = None
        else:
            objectOfTracker = ObjectTracker(trackerName)
    else:
        pass
    
    if trackerName != None and objectOfTracker:
        mot_tracker = objectOfTracker.trackerObject.mot_tracker
    else:
        mot_tracker = None
    print('Loading {} with {} labels.'.format(args.model, args.labels))
    interpreter = make_interpreter(args.model)
    interpreter.allocate_tensors()
    labels = read_label_file(args.labels)
    inference_size = input_size(interpreter)

    if args.videosrc=='dev': 
        cap = cv2.VideoCapture(args.camera_idx)
    elif args.videosrc=='file':
        cap = cv2.VideoCapture(args.filesrc)    
    else:
        if args.netsrc==None:
            print("--videosrc was set to net but --netsrc was not specified")
            sys.exit()
        cap = cv2.VideoCapture(args.netsrc)    

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: 
            if args.videosrc=='file':
                cap = cv2.VideoCapture(args.filesrc)
                continue  
            else:
                break
        cv2_im = frame

        cv2_im_rgb = cv2.cvtColor(cv2_im, cv2.COLOR_BGR2RGB)
        cv2_im_rgb = cv2.resize(cv2_im_rgb, inference_size)
        run_inference(interpreter, cv2_im_rgb.tobytes())
        objs = get_objects(interpreter, args.threshold)[:args.top_k]
        height, width, channels = cv2_im.shape
        scale_x, scale_y = width / inference_size[0], height / inference_size[1]
        detections = []  # np.array([])
        for obj in objs:
            bbox = obj.bbox.scale(scale_x, scale_y)
            element = []  # np.array([])
            element.append(bbox.xmin)
            element.append(bbox.ymin)
            element.append(bbox.xmax)
            element.append(bbox.ymax)
            element.append(obj.score)  # print('element= ',element)
            element.append(obj.id)
            detections.append(element)  # print('dets: ',dets)
        # convert to numpy array #      print('npdets: ',dets)
        detections = np.array(detections)
        trdata = []
        trackerFlag = False
        if detections.any():
            if mot_tracker != None:
                trdata = mot_tracker.update(detections)
                trackerFlag = True

        cv2_im = append_objs_to_img(cv2_im,  detections, labels, trdata, trackerFlag)
        
        if args.display == 'True':
            cv2.imshow('frame', cv2_im)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

def append_objs_to_img(cv2_im,  objs, labels, trdata, trackerFlag):

    if trackerFlag and (np.array(trdata)).size:
        for td in trdata:
            x0, y0, x1, y1, trackID = int(td[0].item()), int(td[1].item()), int(td[2].item()), int(td[3].item()), td[4].item()
            overlap = 0
            for ob in objs:
                dx0, dy0, dx1, dy1 = int(ob[0].item()), int(ob[1].item()), int(ob[2].item()), int(ob[3].item())
                area = (min(dx1, x1)-max(dx0, x0))*(min(dy1, y1)-max(dy0, y0))
                if (area > overlap):
                    overlap = area
                    obj = ob

            obj_score = obj[4].item()
            obj_id = int(obj[5].item())
            percent = int(100 * obj_score)
            label = '{}% {} ID:{}'.format(
                percent, labels.get(obj_id, obj_id), int(trackID))
            cv2_im = cv2.rectangle(cv2_im, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2_im = cv2.putText(cv2_im, label, (x0, y0+30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)

    else:
        for obj in objs:
            x0, y0, x1, y1 = int(obj[0].item()), int(obj[1].item()), int(obj[2].item()), int(obj[3].item())
            obj_score = obj[4].item()
            obj_id = int(obj[5].item())

            percent = int(100 * obj_score)
            label = '{}% {}'.format(percent, labels.get(obj_id, obj_id))

            cv2_im = cv2.rectangle(cv2_im, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2_im = cv2.putText(cv2_im, label, (x0, y0+30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), 2)
    return cv2_im

if __name__ == '__main__':
    main()
