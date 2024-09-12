import sys
import board
from storage import VfsFat, mount, remount
from digitalio import DigitalInOut
from adafruit_sdcard import SDCard

vfs = VfsFat(SDCard(board.SPI(), DigitalInOut(board.SD_CS)))
mount(vfs, "/sd")

sys.path.append("/sd")
sys.path.append("/sd/lib")

import main

