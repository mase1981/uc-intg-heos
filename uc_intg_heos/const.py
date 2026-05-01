"""
HEOS Integration constants.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

POLL_INTERVAL = 10
POLL_INTERVAL_STANDBY = 30
UPDATE_THROTTLE = 2.0

AVR_KEYWORDS = ["avr", "receiver", "denon avr", "marantz sr", "marantz nr"]

INPUT_COMMAND_MAP = {
    "INPUT_HDMI_ARC": "inputs/hdmi_arc_1",
    "INPUT_HDMI_1": "inputs/hdmi_in_1",
    "INPUT_HDMI_2": "inputs/hdmi_in_2",
    "INPUT_HDMI_3": "inputs/hdmi_in_3",
    "INPUT_HDMI_4": "inputs/hdmi_in_4",
    "INPUT_OPTICAL": "inputs/optical_in_1",
    "INPUT_COAXIAL": "inputs/coax_in_1",
    "INPUT_AUX": "inputs/aux_in_1",
    "INPUT_BLUETOOTH": "inputs/bluetooth",
}
