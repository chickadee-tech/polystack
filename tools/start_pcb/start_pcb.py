#!/usr/bin/env python

# MIT License
#
# Copyright (c) 2016 Chickadee Tech LLC
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import print_function
from string import Template

import argparse
import math
import copy

import os
import os.path
import shutil

# center 132.75, 92.75 start 130, 92.75
# right 163.25, 92.75
# bottom right 163.25, 123.25
PORT_TO_PINS = {
  "TIM": [(1,), (2,), (3,), (4,)],
  "GPIO": [(5,), (6,), (7,), (8,), (9, ), (10, )],
  "i2c": [(11, 12)],
  "HEIGHT": [(13, 14, 15)],
  "3V3_0.3A_LL": [(16,)],
  "3V3_0.3A_E": [(17,)],
  "+BATT": [(18,)],
  "5V": [(19, 20, 21, 22, 23, 24)],
  "UART": [(39, 40), (37, 38), (35, 36), (33, 34), (31, 32), (29, 30), (27, 28), (25, 26)],
  "TIMG": [(41, 42, 43, 44), (45, 46, 47, 48)],
  "ADC": [(49,), (50,)],
  "GND": [(57, 58, 59, 60, 61, 62, 63, 64)],
  "SDMMC": [(51, 52, 53, 54, 55, 56)],
  "BOOT": [(65, )],
  "RESET": [(66, )],
  "CAN": [(67, 68)],
  "SPI": [(77, 78, 79, 80), (73, 74, 75, 76), (69, 70, 71, 72)]
}

PORT_SUFFIX = {
  "TIM": ("",),
  "GPIO": ("",),
  "i2c": ("SDA", "SCL"),
  "HEIGHT": ("4", "2", "1"),
  "3V3_0.3A_LL": ("",),
  "3V3_0.3A_E": ("",),
  "+BATT": ("",),
  "5V": ("", "", "", "", "", ""),
  "UART": ("TX", "RX"),
  "TIMG": ("CH1", "CH2", "CH3", "CH4"),
  "ADC": ("",),
  "GND": ("", "", "", "", "", "", "", ""),
  "SDMMC": ("D0", "D1", "D2", "D3", "CK", "CMD"),
  "BOOT": ("", ),
  "RESET": ("", ),
  "CAN": ("HI", "LO"),
  "SPI": ("NSS", "SCK", "MISO", "MOSI"),
}

PORT_INTERNAL = ["si2c", "3V3_0.3A_LL"]

SINGLE_USE_PORTS = ["ADC", "UART", "GPIO", "SPI", "SDMMC", "xi2c", "TIM", "TIMG"]
SHARED_PORTS = ["si2c"]
IO_PORT = ["HEIGHT"]
POWER_PORT = ["+BATT", "5V", "3V3", "GND"]

MANUALLY_DONE = ["HEIGHT", "5V", "GND"]
MANUAL_TRACE = ["HEIGHT"]

def to_mils(mm):
  return mm * 39.37

def to_mm(mils):
  return mils / 39.37

def pcb_distance(s):
  if s.endswith("mm"):
    return to_mils(float(s[:-2]))
  elif not s.endswith("mils"):
    print("End the argument")
    # TODO(tannewt): Throw an ArgumentError
  return float(s[:-4])

parser = argparse.ArgumentParser()
parser.add_argument("--annular_ring", default=7, type=pcb_distance)
parser.add_argument("--drill_size", default=13, type=pcb_distance)
parser.add_argument("--min_trace_width", default=6, type=pcb_distance)
parser.add_argument("--min_clearance", default=6, type=pcb_distance)
parser.add_argument("--receptacle_pad_width", default=to_mils((3.78 - 2.38) / 2), type=pcb_distance)
parser.add_argument("--receptacle_pad_height", default=to_mils(0.2),type=pcb_distance)
parser.add_argument("--receptacle_pad_row_separation", default=to_mils(2.38), type=pcb_distance)
parser.add_argument("--receptacle_keepout_width", default=to_mils((2.38 - 0.98) / 2), type=pcb_distance)
parser.add_argument("--header_end_pad_height", default=to_mils(0.35), type=pcb_distance)
parser.add_argument("--header_pad_width", default=to_mils((3.37 - 2.05) / 2), type=pcb_distance)
parser.add_argument("--header_pad_height", default=to_mils(0.23), type=pcb_distance)
parser.add_argument("--header_pad_row_separation", default=to_mils(2.05), type=pcb_distance)
parser.add_argument("--board_type", default="expansion", choices=["fc", "power", "expansion", "top"])
parser.add_argument("--pad_pitch", default=to_mils(0.4), type=pcb_distance)
parser.add_argument("--total_pins", default=80, type=int)
parser.add_argument("--used_ports", nargs="+")
parser.add_argument("--output_directory")
args = parser.parse_args()

pin_info = {}
for pin in range(1, args.total_pins + 1):
  pin_port = None
  for port in PORT_TO_PINS:
    for i, instance in enumerate(PORT_TO_PINS[port]):
      if pin in instance:
        pin_port = port
        suffix = PORT_SUFFIX[port][instance.index(pin)]
        if suffix:
          suffix = "_" + suffix
        if port in SINGLE_USE_PORTS:
          name = port + str(i + 1) + suffix
        else:
          name = port + suffix
  pin_info[pin] = {"state": "untouched", "port": pin_port, "name": name, "nc-out": False}
if args.used_ports:
  next_port = {}
  for port in args.used_ports:
    if port not in next_port:
      next_port[port] = 0

    used_pins = PORT_TO_PINS[port][next_port[port]]

    for pin in used_pins:
      if port in SINGLE_USE_PORTS:
        pin_info[pin]["state"] = "consumed"
      elif port in IO_PORT:
        pin_info[pin]["state"] = "io"
      else:
        pin_info[pin]["state"] = "used"

    next_port[port] += 1

  for port in next_port:
    if port not in SINGLE_USE_PORTS:
      continue
    shifted_ports = PORT_TO_PINS[port][next_port[port]:]
    num_shifted = next_port[port]
    for i, shifted_port in enumerate(shifted_ports):
      for pin in shifted_port:
        pin_info[pin]["state"] = "shifted"
        pin_info[pin]["shift"] = num_shifted * len(shifted_port)
        if len(shifted_ports) - i <= num_shifted:
          pin_info[pin]["nc-out"] = True

first_receptacle_row_x = 6224.80315
first_receptacle_pad_y = 3944.88189

schematic_contents = []
pcb_contents = []
port_contents = []

trace_origins = []

# First row of pads
for i in xrange(args.total_pins / 2):
  pad_y = first_receptacle_pad_y + args.pad_pitch * i

  trace_origins.append((first_receptacle_row_x - args.receptacle_pad_width / 2, pad_y))

second_receptacle_row_x = first_receptacle_row_x + args.receptacle_pad_row_separation + args.receptacle_pad_width

# Second row of pads
for i in xrange(args.total_pins / 2):
  pad_y = first_receptacle_pad_y + args.pad_pitch * i
  trace_origins.append((second_receptacle_row_x + args.receptacle_pad_width / 2, pad_y))

first_header_row_x = first_receptacle_row_x
first_header_pad_y = first_receptacle_pad_y

used_pins = []
internal_connection_count = 0
for i in xrange(args.total_pins):
  trace_x, trace_y = trace_origins[i]

  offset_from_top = (i % (args.total_pins / 2))
  offset_from_center = offset_from_top - args.total_pins / 4
  if offset_from_center >= 0:
    offset_from_center += 1

  x_direction = -1
  if i >= args.total_pins / 2:
    x_direction = 1

  y_direction = offset_from_center / abs(offset_from_center)

  this_pin_info = pin_info[i + 1]
  pin_state = this_pin_info["state"]

  print(this_pin_info)
  schematic_in_x = 2150
  schematic_out_x = 5450
  if x_direction > 0:
    schematic_in_x = 3550
    schematic_out_x = 6850
  if pin_state == "used" or pin_state == "consumed":
    side = ("L", 9300)
    if x_direction > 0:
      side = ("R", 10500)
    offset_shift = 4
    # The 3V3 and BATT pins are inside the HEIGHT pins which should never be used so we reduce our shift.
    if i+1 >= 16 and i + 1 <= 18:
      offset_shift = 2
    used_pins.append((this_pin_info["name"], side[0], side[1], 3800 + y_direction * 100 * (abs(offset_from_center) - offset_shift)))
    rotation = 0
    if i >= args.total_pins / 2:
      rotation = 2
    port_contents.append("Text HLabel {0} {1} {2}    60   Input ~ 0\n{3}".format(schematic_in_x, 1700 + 100 * offset_from_top, rotation, this_pin_info["name"]))
    if pin_state == "used":
      port_contents.append("Text HLabel {0} {1} {2}    60   Input ~ 0\n{3}".format(schematic_out_x, 1700 + 100 * offset_from_top, rotation, this_pin_info["name"]))
      if this_pin_info["port"] in PORT_INTERNAL:
        if internal_connection_count == 0:
          port_contents.append("Text Notes 4750 6750 0    60   ~ 0\nShared Nets")
        y = 6950 + 100 * internal_connection_count
        port_contents.append("Text Label 5050 {0} 0    60   ~ 0\n{1}".format(y, this_pin_info["name"]))
        port_contents.append("Wire Wire Line\n5050 {0} 4950 {0}".format(y))
        port_contents.append("Text HLabel 4950 {0} 0    60   Input ~ 0\n{1}".format(y, this_pin_info["name"]))
        internal_connection_count += 1
  elif this_pin_info["port"] not in MANUALLY_DONE:
    rotation = 2
    if i >= args.total_pins / 2:
      rotation = 0
    port_contents.append("Text Label {0} {1} {2}    60   ~ 0\n{3}".format(schematic_in_x, 1700 + 100 * offset_from_top, rotation, this_pin_info["name"]))
    shift = 0
    if pin_state == "shifted":
      shift = this_pin_info["shift"]
    port_contents.append("Text Label {0} {1} {2}    60   ~ 0\n{3}".format(schematic_out_x, 1700 + 100 * (offset_from_top + y_direction * shift), rotation, this_pin_info["name"]))
    if this_pin_info["nc-out"]:
      port_contents.append("NoConn ~ {0} {1}".format(schematic_out_x, 1700 + 100 * (offset_from_top)))

  input_trace = None
  output_trace = None

  if abs(offset_from_center) == 20:
    via_x = trace_x - x_direction * (args.annular_ring + args.min_clearance + args.drill_size / 2.)
    via_y = trace_y + y_direction * (args.annular_ring + args.min_clearance + args.drill_size / 2. + (args.header_end_pad_height - args.receptacle_pad_height / 2.) + args.pad_pitch)
    via = (via_x, via_y)
    input_trace = [(via_x, trace_y),
                    (via_x, via_y)]
    if pin_state == "untouched":
      output_trace = input_trace
    if args.board_type == "fc":
      input_trace = []
  else:
    minimum_angle = math.asin((args.min_trace_width + args.min_clearance) / args.pad_pitch)
    angle_shift = args.pad_pitch * math.cos(minimum_angle)
    start_y = trace_y - y_direction * (args.receptacle_pad_height - args.min_trace_width) / 2.

    no_trace_via_distance = args.min_clearance + 2. * args.annular_ring + args.drill_size
    via_distance = 2. * args.min_clearance + 2. * args.annular_ring + args.drill_size + args.min_trace_width
    annular_distance = 2. * args.min_clearance + 2. * args.min_trace_width
    distance_down_slant = ((via_distance ** 2 - annular_distance ** 2 - 3) ** 0.5) / 2.
    side = -1
    if abs(offset_from_center) > 15:
      a = args.min_clearance + args.annular_ring + args.drill_size / 2.
      b = args.drill_size / 2. + args.annular_ring - args.min_trace_width / 2.
      c = b / math.sin(math.pi / 2. - minimum_angle)
      d = b / math.tan(math.pi / 2. - minimum_angle)
      e = (a + c) / math.sin(minimum_angle)
      top_shift_down = e - d
      side = 1
      distance_down_slant += angle_shift
      total_distance_down_slant = (20 - abs(offset_from_center) - 1) * distance_down_slant + top_shift_down
      angle_from_anchor = minimum_angle + (math.pi / 2)
      via_angle = minimum_angle + side * math.atan(1. * (args.min_clearance + args.min_trace_width + 6.25) / (distance_down_slant))
    else:
      a = args.min_clearance / 2. + args.annular_ring + args.drill_size / 2. - args.min_trace_width / 2. - (args.pad_pitch - args.receptacle_pad_height) / 2.
      b = args.drill_size / 2. + args.annular_ring - args.min_trace_width / 2.
      c = b / math.tan(minimum_angle)
      d = b / math.sin(minimum_angle)
      e = (d + a) / math.cos(minimum_angle)
      shift_down = e - c
      distance_down_slant -= angle_shift
      total_distance_down_slant = (abs(offset_from_center) - 1) * distance_down_slant + shift_down
      angle_from_anchor = minimum_angle - (math.pi / 2)
      via_angle = minimum_angle + side * math.atan(1. * (distance_down_slant - 1.5 ** 0.5) / (args.min_clearance + args.min_trace_width))

    # Shift outwards in the middle.
    anchor_x = trace_x + x_direction * total_distance_down_slant * math.sin(minimum_angle)
    anchor_y = start_y + y_direction * total_distance_down_slant * math.cos(minimum_angle)

    distance_from_anchor = args.drill_size / 2. + (args.annular_ring - args.min_trace_width) + args.min_trace_width / 2.
    from_anchor_x = x_direction * distance_from_anchor * math.sin(angle_from_anchor)
    from_anchor_y = y_direction * distance_from_anchor * math.cos(angle_from_anchor)

    if abs(offset_from_center) % 2 == 0:
      shift_out = (no_trace_via_distance ** 2 - (via_distance / 2.) ** 2) ** 0.5

      blue_dot = (anchor_x - from_anchor_x, anchor_y - from_anchor_y)

      purple_dot_x = blue_dot[0] + x_direction * shift_out * math.sin(via_angle - side * math.pi / 2.)
      purple_dot_y = blue_dot[1] + y_direction * shift_out * math.cos(via_angle - side * math.pi / 2.)

      # shorten from the red dot back
      anchor_x -= x_direction * args.min_trace_width * math.sin(minimum_angle)
      anchor_y -= y_direction * args.min_trace_width * math.cos(minimum_angle)

      via = (purple_dot_x, purple_dot_y)
      input_trace = [[trace_x - x_direction * args.receptacle_pad_width / 2, start_y],
                     [trace_x, start_y],
                     (anchor_x, anchor_y),
                     blue_dot,
                     (via)]
      if pin_state == "untouched" or pin_state == "used":
        output_trace = input_trace
    else:
      via = [anchor_x - from_anchor_x, anchor_y - from_anchor_y]
      input_trace = [[trace_x - x_direction * args.receptacle_pad_width / 2, start_y],
                     [trace_x, start_y],
                     (anchor_x, anchor_y),
                     via]
      if pin_state == "untouched" or pin_state == "used":
        output_trace = input_trace

    if pin_state == "shifted":
      output_trace = copy.deepcopy(input_trace)
      anchor = output_trace[2]
      shift_distance = this_pin_info["shift"] * (args.min_clearance + args.min_trace_width)
      output_trace.insert(2, (anchor[0] + x_direction * shift_distance * math.sin(angle_from_anchor),
                              anchor[1] + y_direction * shift_distance * math.cos(angle_from_anchor)))
      output_trace[1][1] += y_direction * this_pin_info["shift"] * (args.pad_pitch)
      output_trace[0][1] += y_direction * this_pin_info["shift"] * (args.pad_pitch)

  if this_pin_info["port"] in MANUAL_TRACE:
    continue

  if pin_state != "consumed":
    # (via (at 167.43 128.69) (size 0.6858) (drill 0.3302) (layers F.Cu B.Cu) (net 0))
    pcb_contents.append("(via (at {0} {1}) (size {2}) (drill {3}) (layers {4}) (net {5}))".format(to_mm(via[0]), to_mm(via[1]), to_mm(args.annular_ring * 2. + args.drill_size), to_mm(args.drill_size), "F.Cu B.Cu", 0))

  if input_trace:
    layers = []
    if args.board_type != "fc":
      layers = ["B.Cu"]
    elif args.board_type == "fc" and i >= args.total_pins / 2:
      layers = ["B.Cu"]
    for i, point in enumerate(input_trace[1:]):
      for layer in layers:
        pcb_contents.append("(segment (start {0} {1}) (end {2} {3}) (width {4}) (layer {5}) (net {6}))".format(to_mm(input_trace[i][0]), to_mm(input_trace[i][1]), to_mm(point[0]), to_mm(point[1]), to_mm(args.min_trace_width), layer, 0))

  if output_trace:
    for p, point in enumerate(output_trace[1:]):
      pcb_contents.append("(segment (start {0} {1}) (end {2} {3}) (width {4}) (layer {5}) (net {6}))".format(to_mm(output_trace[p][0]), to_mm(output_trace[p][1]), to_mm(point[0]), to_mm(point[1]), to_mm(args.min_trace_width), "F.Cu", 0))

used_pin_count = 0

for pin in sorted(used_pins, key=lambda x: x[3]):
  if used_pin_count == 0:
    # Append an initial empty string so we get a leading newline. We can't
    # have a blank line in the file because then it won't load.
    schematic_contents.append("")
  schematic_contents.append("F{0} \"{1}\" I {2} {3} {4} 60".format(used_pin_count + 4, *pin))
  used_pin_count += 1

pcb_template = ""
schematic_template = ""
port_template = ""
project_file = ""
filename_placeholder = ""
if args.board_type == "fc":
  pass
elif args.board_type == "power":
  pass
elif args.board_type == "expansion":
  pcb_template = "templates/polystack_mod/FCExpansion.kicad_pcb.template"
  schematic_template = "templates/polystack_mod/FCExpansion.sch.template"
  port_template = "templates/polystack_mod/ExpansionPort.sch.template"
  project_file = "templates/polystack_mod/FCExpansion.pro"
  fp_lib_file = "templates/polystack_mod/fp-lib-table"
  filename_placeholder = "FCExpansion"
elif args.board_type == "top":
  pass

full_output_dir = os.path.join(args.output_directory, "pcb")
if not os.path.isdir(full_output_dir):
  os.makedirs(full_output_dir)

project_title = os.path.basename(args.output_directory)
project_fn = os.path.join(full_output_dir,
                          project_title + ".pro")
shutil.copyfile(project_file, project_fn)
shutil.copyfile(fp_lib_file, os.path.join(full_output_dir, "fp-lib-table"))
for template_fn, contents in [(pcb_template, pcb_contents),
                              (schematic_template, schematic_contents),
                              (port_template, port_contents)]:
  with open(template_fn, "r") as f:
    template = Template(f.read())
    filled = template.substitute({"content": "\n".join(contents), "title": project_title})
    fn = os.path.join(full_output_dir, os.path.basename(template_fn)[:-len(".template")].replace(filename_placeholder, project_title))
    with open(fn, "w") as out:
      out.write(filled)
