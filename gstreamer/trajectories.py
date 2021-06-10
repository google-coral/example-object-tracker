import csv
import hashlib
from collections import namedtuple, defaultdict
from .geometry import segments_intersection

DetectedObject = namedtuple('DetectedObject', 'id label x y w h cx cy score')

def id_to_random_color(number):
  numByte = str.encode(str(number))
  hashObj = hashlib.sha1(numByte).digest()
  r, g, b = hashObj[-1] % 255.0, hashObj[-2] % 255.0, hashObj[-3] % 255.0
  return int(r), int(g), int(b)

class ObjTrajectories:
  def __init__(self) -> None:
    self.objs_dict = defaultdict(lambda: [])
    self._cross_counter = 0
    self.cross_segment = None

  def set_cross_segment(self, src_w, src_h):
    self.cross_segment = (
      (src_w / 2, 0),
      (0, src_h / 2)
    )

  def update_obj_traj_dict(self, label, x, y, w, h, track_id, score):
    cx, cy = x + w / 2, y + h / 2
    detectedObject = DetectedObject(label, x, y, w, h, cx, cy, score)
    self.objs_dict[track_id].append(detectedObject)
    self._detect_if_object_has_crossed(track_id)

  def add_obj_traj_to_drawing(self, obj_id, drawing):
    prev_cx, prev_cy = None, None
    for box in self.objs_dict[obj_id]:
      color = 'rgb({},{},{})'.format(*id_to_random_color(obj_id))
      cx, cy = box.x + box.w / 2, box.y + box.h / 2
      drawing.circle(center=(cx, cy), r=3, fill=color)
      if prev_cx is not None:
        drawing.line(start=(prev_cx, prev_cy), end=(cx, cy), stroke=color, stroke_width='2')
      prev_cx, prev_cy = cx, cy

  def save_csv(self, filename):
    with open(filename, 'w') as csvfile:
      writer = csv.DictWriter(csvfile, fieldnames=DetectedObject._fields)
      writer.writeheader()
      for obj in self.objs_dict.values():
        for box in obj:
          writer.writerow(box._asdict())

  def _detect_if_object_has_crossed(self, track_id):
    if self.cross_segment is None:
      return
    points = self.objs_dict[track_id]
    segments = ObjTrajectories.build_segments_from_points(points)
    if len(segments) < 1:
      return
    last_segment = segments[-1]
    intersection = segments_intersection(last_segment, self.cross_segment)
    if intersection is not None:
      self._cross_counter += 1

  def build_segments_from_points(points):
    prev_point_coords = None
    segments = []
    for p in points:
      if prev_point_coords is not None:
        segments.append(prev_point_coords, (p.cx, p.cy))
      prev_point_coords = (p.cx, p.cy)
    return segments

  def update_swg_drawing(self, drawing):
    for track_id, obj in self.objs_dict.items():
      color = 'rgb({},{},{})'.format(*id_to_random_color(track_id))
      segments = ObjTrajectories.build_segments_from_points(obj)
      for s in segments:
        p1, p2 = s
        if s is segments[0]:
          drawing.add(drawing.circle(center=p1, r=10, fill=color))
        drawing.add(drawing.line(start=p1, end=p2, stroke=color, stroke_width='3'))
        drawing.add(drawing.circle(center=p2, r=10, fill=color))
    drawing.add(drawing.text('Counter {}'.format(self._cross_counter), insert=(10, 10), fill='black', font_size=20))
    self.save_csv('/tmp/traj.csv')
