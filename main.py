import network
import time
import json
import re
import uasyncio as asyncio
from machine import Pin, PWM, Timer
from micropython import const
import sys

# Wi-Fi network connection info
SSID = const('wifi-name')
PASSWORD = const('wifi-password')
PORT = const(80)

outputs = [0, 0, 0, 0]  # 0=off, 1=on, 0<x<1=low frequency pwm, up to four loads supported
inversed_outputs = True  # The load is on when the output pin is in the 0 state.
max_pwm_time = 30  # PWM period in tenths of a second
pwm_time = 0

event_handlers = []  # Event condition and commands to be executed in case of the event

messenger = None  # Message to user by led or buzzer

buzzer = PWM(Pin(22))  # Piezo buzzer is connected to GP22.
buzzer.freq(1000)
buzzer.duty_u16(0)
led = Pin('LED', Pin.OUT)

key_pins = []  # keys connected to GP0...GP3
for i in [0, 1, 2, 3]:
    key_pins.append(Pin(i, Pin.IN, Pin.PULL_UP))

load_pins = []  # pins GP4...GP7 are used to control the output loads
for i in [4, 5, 6, 7]:
    pin = Pin(i, Pin.OUT, value=inversed_outputs)
    load_pins.append(pin)

# LED flashes or a buzzer beeps sequence generator
class LedBeepMessenger:

    # pattern is a list with on/off states durations
    def __init__(self, pattern, outputFn, repeatCount=None):
        self.pos = 0
        self.count = repeatCount
        self.pattern = pattern
        self.period = 0
        for p in pattern:
            self.period = self.period + p
        self.outputFn = outputFn

    # When the sequence has been completed (return True), the generator will be deleted.
    def on_timer(self):
        pos = self.pos % self.period
        active = True
        for stepLen in self.pattern:
            if pos < stepLen:
                self.outputFn(active)
                break
            pos = pos - stepLen
            active = not active
        self.pos = self.pos + 1
        if self.count is None:  # if no count specified, generate forever
            return False
        return self.pos >= self.period * self.count


def tick(timer):
    global messenger, pwm_time, max_pwm_time, load_pins
    if type(messenger) is LedBeepMessenger:
        if messenger.on_timer():
            messenger = None

    for i in range(4):
        state = outputs[i] * max_pwm_time > pwm_time
        load_pins[i].value(state != inversed_outputs)
    pwm_time = pwm_time + 1
    if pwm_time >= max_pwm_time:
        pwm_time = 0


tim = Timer()
tim.init(freq=10, mode=Timer.PERIODIC, callback=tick)


class SetLoadState:

    def __init__(self, channel, powerValue):
        self.power = powerValue
        self.channel = channel

    def start(self):
        print(f'output[{self.channel}]={self.power}')
        outputs[self.channel] = self.power

    def poll(self):
        return True


class Wait: # wait for a specified number of seconds

    def __init__(self, duration):
        if duration > 24 * 3600:
            raise RuntimeError("wait time > 24 hours")
        self.duration = duration

    def start(self):
        self.deadline = time.ticks_add(time.ticks_ms(), self.duration * 1000)

    def poll(self):
        return time.ticks_diff(time.ticks_ms(), self.deadline) >= 0


class SayToUser:

    def __init__(self, soundIndex):
        self.index = soundIndex

    def start(self):
        global messenger, led
        led.off()
        buzzer.duty_u16(0)

        if 1 <= self.index and self.index <= 9: # flash led n times
            messenger = LedBeepMessenger([2, 5], lambda x: led.value(x), self.index)
        if 41 <= self.index and self.index <= 49: # flash led n times, pause and repeat forever
            pattern = []
            for i in range(self.index-40):
                pattern.append(2)
                pattern.append(3)
            pattern[-1] = 12
            messenger = LedBeepMessenger(pattern, lambda x: led.value(x))
        elif 51 <= self.index and self.index <= 59: # beep n times
            messenger = LedBeepMessenger([3, 3], lambda x: buzzer.duty_u16(32768 if x else 0), self.index-50)
        elif self.index == 81:
            messenger = LedBeepMessenger([2, 8], lambda x: led.value(x))
        elif self.index == 82:
            messenger = LedBeepMessenger([2, 1, 2, 8], lambda x: led.value(x))
        elif self.index == 83:
            messenger = LedBeepMessenger([2, 1, 2, 1, 2, 8], lambda x: led.value(x))
        elif self.index == 88:
            messenger = LedBeepMessenger([1, 1, 1, 1, 1, 3], lambda x: buzzer.duty_u16(32768 if x else 0), 2)
        else:
            messenger = None

    def poll(self):
        return True


class Halt(SetLoadState):  # Stop all command forever and put off all the loads. Not yet implemented.

    def __init__(self):
        super(Halt, self).__init__(0.0)

    def start(self):
        SetLoadState.start()
        # TODO stop polling


class EventHandler:

    def __init__(self):
        self.cmdIndex = None
        self.commands = []

    def poll(self):

        if self.cmdIndex is None:  # waiting for the event to start executing commands
            if self.test_condition():
                self.cmdIndex = 0
                self.commands[0].start()

        elif self.cmdIndex < len(self.commands):  # commands is running
            if self.commands[self.cmdIndex].poll():
                self.cmdIndex = self.cmdIndex + 1
                if self.cmdIndex < len(self.commands):
                    self.commands[self.cmdIndex].start()

        else:  # all commands finished, wait the condition for finish (e.g. release button) to restart the iteration
            if self.test_condition() == False:
                self.cmdIndex = None

    def init_commands(self, cmdString):
        s = cmdString
        p = re.compile(r"([a-z]+)([0-9\.]+)(.*)")

        while len(s) > 0:
            m = p.search(s)
            cmd_name = m.group(1)
            cmd_args = m.group(2)
            s = m.group(3)

            if "abcd".find(cmd_name) >= 0 and len(cmd_name) == 1:
                cmd = SetLoadState("abcd".find(cmd_name), float(cmd_args))
            elif cmd_name == 'w':
                cmd = Wait(int(cmd_args))
            elif cmd_name == 's':
                cmd = SayToUser(int(cmd_args))
            elif cmd_name == 'halt':
                cmd = Halt()
            else:
                raise RuntimeError('Unknown Command (' + cmd_name + ')')

            self.commands.append(cmd)


class RunImmediatelyCommands(EventHandler): # for run commands just after upload or restart

    def __init__(self):
        super(RunImmediatelyCommands, self).__init__()

    def test_condition(self):
        return True


class OnTimeCommands(EventHandler): # Run commands at specified time. Not implemented yet.

    # no prefix, data is 4..11 numbers: 01234567(optional weekdays)1245(start time)
    def __init__(self, s):
        super(OnTimeCommands, self).__init__()
        if 4 <= len(s) and len(s) <= 11 and re.match("^[0-9]+$", s):
            self.startTime = int(s[-4:])
            self.days = s[:-4].replace("0", "7")  # Sunday can be written as "0" or "7"
            print(self.days)
        else:
            raise RuntimeError("event time format error")

    def test_condition(self):
        return False


class OnKeypressedCommands(EventHandler):
    prefix = 'key'

    def __init__(self, str):
        super(OnKeypressedCommands, self).__init__()
        self.keyIndex = int(str[len(OnKeypressedCommands.prefix):])

    def test_condition(self):
        return key_pins[self.keyIndex].value() == 0


class OnLoadOffCommands(EventHandler):  # On connect/disconnect load. Not implemented yet.
    prefix = 'off'

    def __init__(self, str):
        super(OnLoadOffCommands, self).__init__()

    def test_condition(self):
        return False


def parseCommand(str, atUpload):
    newEvents = []
    evtStrings = str.lower().split('@')
    print(f"start parsing: {str}, at upload: {atUpload}")
    for evt in evtStrings:
        ss = evt.split(':')
        evtHeader = ss[0]
        if len(ss) == 1:
            if atUpload:
                newEvents.append(RunImmediatelyCommands())
            else:
                continue
        elif len(ss) == 2:
            if evtHeader.startswith(OnKeypressedCommands.prefix):
                newEvents.append(OnKeypressedCommands(evtHeader))
            elif evtHeader.startswith(OnLoadOffCommands.prefix):
                newEvents.append(OnLoadOffCommands(evtHeader))
            elif evtHeader.startswith('reset'):
                if not atUpload:
                    newEvents.append(RunImmediatelyCommands())
                else:
                    continue
            else:
                newEvents.append(OnTimeCommands(evtHeader))

        newEvents[-1].init_commands(ss[-1])
        if len(newEvents[-1].commands) == 0:
            del newEvents[-1]  # delete event without commands

    global event_handlers
    event_handlers = newEvents


new_prog = None  # To transfer data from the server task to the control loads task


async def main_plug_loop():
    try:
        f = open('program', 'r')
        prog = f.readline()
        parseCommand(prog, False)
        print('program started:', prog)
        f.close()
    except Exception as e:
        print('no program loaded:', e)

    while True:

        try:
            global new_prog
            if new_prog:
                print('new program detected')
                parseCommand(new_prog, True)
                f = open('program', 'w')  # save data only if it has been accepted (no exception)
                prog = f.write(new_prog)
                f.close()
                new_prog = None

            for evt in event_handlers:
                try:
                    evt.poll()
                except Exception as e:
                    sys.print_exception(e)

            await asyncio.sleep(1)

        except Exception as e:
            sys.print_exception(e)


def make_config():
    cfg = {}
    try:
        f = open('program', 'r')
        prog = f.readline()
        cfg['program'] = prog
        f.close()
    except:
        pass
    cfg['version'] = '1.0'
    cfg['keyCount'] = 1
    cfg['outCount'] = 1
    return cfg

wlan = network.WLAN(network.STA_IF)

def wait_for_network():
    wlan.active(True)
    wlan.config(pm=0xa11140)  # Disable power-save mode

    while True:
        for info in wlan.scan():
            if info[0].decode() == SSID:
                return
        time.sleep(1)


def send_file(writer, fileName):
    try:
        f = open(fileName, 'r')
        if fileName[-4:] == '.svg':
            writer.write('HTTP/1.0 200 OK\r\nContent-type: image/svg+xml\r\n\r\n')
        else:
            writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')

        line = f.readline()
        while line:
            writer.write(line)
            line = f.readline()
        f.close()
    except OSError as e:
        writer.write('HTTP/1.0 404 Not Found\r\n\r\n')
        writer.write('<html><head><title>404 Not Found</title></head><body>404 Not Found</body></html>\r\n\r\n')


def connect_to_network():
    wlan.connect(SSID, PASSWORD)

    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('waiting for connection...')
        time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError('network connection failed')
    else:
        print('connected')
        status = wlan.ifconfig()
        print('ip = ' + status[0])


async def serve_client(reader, writer):
    try:
        conn_info = reader.get_extra_info('peername')
        print("Client connected", conn_info)

        request_line = None
        while True:
            line = await reader.readline()
            if not line:
                raise RuntimeError("Connection lost")
            if not request_line:
                request_line = line
                print("Request:", request_line)
            if line == b"\r\n":
                break

        m = re.match("^GET \/([\w\.\-]+)(|\?.+) HTTP", request_line.decode())

        page_name = 'index.htm'
        if m:
            page_name = m.group(1).lower()
            args = m.group(2)
            if args:
                args = args[1:]

        if page_name == "setprog":
            writer.write('HTTP/1.0 200 OK\r\nContent-type: application/json\r\n\r\n')
            global new_prog
            new_prog = args
            writer.write('{"Result":"Ok"}')
        elif page_name == 'cfg.js':
            writer.write('HTTP/1.0 200 OK\r\nContent-type: application/javascript\r\n\r\n')
            writer.write('let CFG=' + json.dumps(make_config()))
        else:
            send_file(writer, page_name)

        await writer.drain()
        await writer.wait_closed()
        print("Client disconnected", conn_info)

    except Exception as e:
        sys.print_exception(e)


async def main():
    print('Waiting Network...')
    wait_for_network()
    print('Connecting to Network...')
    connect_to_network()

    asyncio.create_task(main_plug_loop())

    print('Setting up webserver...')
    server = await asyncio.start_server(serve_client, "0.0.0.0", PORT)
    await server.wait_closed()
    print("SERVER CLOSED")


while True:
    try:
        asyncio.run(main())
    finally:
        asyncio.new_event_loop()
