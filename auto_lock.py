import RPi.GPIO as GPIO
import time
import asyncio
from enum import Enum
from ds3225_client import DS3225Client       # モーター
from rc522_client import RC522Client         # RFIDリーダー
from switch_client import SWITCHClient
from LINE_client import LINEClient
from google_home import google_home

UNLOCKED_DEG = 175
LOCKED_DEG = 85
UNLOCKED_TIME = 10
DISTANCE = 50
NOTIFTY_INTERVAL = 300

rc522 = RC522Client()
ds3225 = DS3225Client()
switch = SWITCHClient()
line = LINEClient()
# RFID認証用鍵の準備
with open("key.txt", "r") as f:
    keys = f.readlines()
keys = [key.strip() for key in keys]
keys = set(keys)

async def authenticate_rfid(loop):
    print("RFID start")
    rc522.id_ = None
    while rc522.id_ not in keys:
        rc522.wait_for_tag(250) #ms
        await asyncio.sleep(0)
    loop.stop()
async def taken_key(loop):
    print("taken_key start")
    while switch.is_opened(26):
        await asyncio.sleep(0)
    while switch.is_closed(26):
        await asyncio.sleep(0)
    loop.stop()
def is_door_opened():
    return switch.is_opened(2)
class State:
    def next_state(self):
        raise NotImplementedError("next_state is abstractmethod")
    def entry_proc(self):
        raise NotImplementedError("entry_proc is abstractmethod")
    def exit_proc(self):
        raise NotImplementedError("exit_proc is abstractmethod")
    def reset(self):
        self.timer = time.time()
class Unlocked(State):
    deg = UNLOCKED_DEG
    def __init__(self):
        self.name = "UNLOCKED"
        self.reset()
    def wait_for_next_state(self):
        print("wait for UNLOCKED_TIME start")
        while (time.time() - self.timer) < UNLOCKED_TIME:
            if is_door_opened():
                self.reset()
            time.sleep(1)
        print("wait for UNLOCKED_TIME finish")
        return "LOCKED"
    def entry_proc(self):
        print("Unlock!")
        self.reset()
        ds3225.set_pos(self.deg)
    def exit_proc(self):
        pass

class Locked(State):
    deg = LOCKED_DEG
    def __init__(self):
        self.name = "LOCKED"
        self.reset()
        self.exit_proc_flag = set()
    def wait_for_next_state(self):
        loop = asyncio.get_event_loop()
        print(asyncio.Task.all_tasks(loop))
        task1 = asyncio.ensure_future(taken_key(loop))
        task2 = asyncio.ensure_future(authenticate_rfid(loop))
        loop.run_forever()
        if task1.done():
            print("Key taken.")
            self.exit_proc_flag.add("GHOME")
        else:
            task1.cancel()
        if task2.done():
            print("RFID authenticated.")
            if time.time() - self.timer > NOTIFTY_INTERVAL:
                print("LINE will be sent.")
                self.exit_proc_flag.add("LINE")
        else:
            task2.cancel()
        return "UNLOCKED"
    def entry_proc(self):
        print("Lock!")
        self.reset()
        ds3225.set_pos(self.deg)
    def exit_proc(self):
        if("LINE" in self.exit_proc_flag):
            asyncio.get_event_loop().run_in_executor(None, line.broadcast, "ただいま帰ったでござる。")
            self.exit_proc_flag.remove("LINE")
        if("GHOME" in self.exit_proc_flag):
            url = "http://localhost:8091/google-home-notifier?text=http%3A%2F%2F192.168.100.105%2Fkenchi.mp3"
            asyncio.get_event_loop().run_in_executor(None, google_home.notify, url)
            self.exit_proc_flag.remove("GHOME")
class Door:
    def __init__(self):
        print('Initializing auto lock system.')
        self.unlocked = Unlocked()
        self.locked = Locked()
        self.states = {self.locked.name: self.locked, self.unlocked.name: self.unlocked}
        self.state = self.unlocked
    def update_state(self):
        self.state.entry_proc()
        next_state = self.state.wait_for_next_state()
        self.state.exit_proc()
        self.state = self.states[next_state]

LED_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
if __name__ == "__main__":
    door = Door()
    while True:
        if door.state is door.unlocked:
            GPIO.output(LED_PIN, GPIO.HIGH)
        door.update_state()
        GPIO.output(LED_PIN, GPIO.LOW)
