__author__ = 'tanel'

import argparse
from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib
import Queue
import json
import time
import os
from math import exp

def rate_limited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rate_limited_function(*args,**kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rate_limited_function
    return decorate


class MyClient(WebSocketClient):

    def __init__(self, audiofile, url, protocols=None, extensions=None, heartbeat_freq=None, byterate=32000,
                 save_adaptation_state_filename=None, send_adaptation_state_filename=None):
        super(MyClient, self).__init__(url, protocols, extensions, heartbeat_freq)
        self.final_hyps = []
        self.audiofile = audiofile
        self.byterate = byterate
        self.final_hyp_queue = Queue.Queue()
        self.save_adaptation_state_filename = save_adaptation_state_filename
        self.send_adaptation_state_filename = send_adaptation_state_filename

    @rate_limited(4)
    def send_data(self, data):
        self.send(data, binary=True)

    def opened(self):
        #print "Socket opened!"
        def send_data_to_ws():
            if self.send_adaptation_state_filename is not None:
                print >> sys.stderr, "Sending adaptation state from %s" % self.send_adaptation_state_filename
                try:
                    adaptation_state_props = json.load(open(self.send_adaptation_state_filename, "r"))
                    self.send(json.dumps(dict(adaptation_state=adaptation_state_props)))
                except:
                    e = sys.exc_info()[0]
                    print >> sys.stderr, "Failed to send adaptation state: ",  e
            with self.audiofile as audiostream:
                for block in iter(lambda: audiostream.read(self.byterate/4), ""):
                    self.send_data(block)
            # print >> sys.stderr, "Audio sent, now sending EOS"
            self.send("EOS")

        t = threading.Thread(target=send_data_to_ws)
        t.start()


    def received_message(self, m):
        response = json.loads(str(m))
        #print >> sys.stderr, "RESPONSE:", response
        #print >> sys.stderr, "JSON was:", m
        if response['status'] == 0:
            if 'result' in response:
                trans = response['result']['hypotheses'][0]['transcript']
                if response['result']['final']:
                    #print >> sys.stderr, trans,
                    self.final_hyps.append(trans)
                    print >> sys.stderr, '\r%s' % trans.replace("\n", "\\n")

                    # Confidence < 30 is not allowed here
                    if len(response["result"]["hypotheses"]) > 1:
                        confidence = response["result"]["hypotheses"][0]["likelihood"] - response["result"]["hypotheses"][1]["likelihood"]
                        confidence = 1 - exp(-confidence)
                    else:
                        confidence = 1.0e+10;
                    if confidence * 100 > 30:
                        self.final_hyps.append(trans)
                    else:
                        self.final_hyps.append('')
                else:
                    print_trans = trans.replace("\n", "\\n")
                    if len(print_trans) > 80:
                        print_trans = "... %s" % print_trans[-76:]
                    print >> sys.stderr, '\r%s' % print_trans,
            if 'adaptation_state' in response:
                if self.save_adaptation_state_filename:
                    print >> sys.stderr, "Saving adaptation state to %s" % self.save_adaptation_state_filename
                    with open(self.save_adaptation_state_filename, "w") as f:
                        f.write(json.dumps(response['adaptation_state']))
        else:
            # print >> sys.stderr, "Received error from server (status %d)" % response['status']
            # if 'message' in response:
            #     print >> sys.stderr, "Error message:",  response['message']
            pass

    def get_full_hyp(self, timeout=90):
        return self.final_hyp_queue.get(timeout)

    def closed(self, code, reason=None):
        #print "Websocket closed() called"
        #print >> sys.stderr
        self.final_hyp_queue.put(" ".join(self.final_hyps))


def main():
    parser = argparse.ArgumentParser(description='Command line client for kaldigstserver')
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/client/ws/speech", dest="uri", help="Server websocket URI")
    parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int, help="Rate in bytes/sec at which audio should be sent to the server. NB! For raw 16-bit audio it must be 2*samplerate!")
    parser.add_argument('--save-adaptation-state', help="Save adaptation state to file")
    parser.add_argument('--send-adaptation-state', help="Send adaptation state from file")
    parser.add_argument('--content-type', default='', help="Use the specified content type (empty by default, for raw files the default is  audio/x-raw, layout=(string)interleaved, rate=(int)<rate>, format=(string)S16LE, channels=(int)1")
    parser.add_argument('audiofile', help="Audio file to be sent to the server", type=argparse.FileType('rb'), default=sys.stdin)
    args = parser.parse_args()

    content_type = args.content_type
    if content_type == '' and args.audiofile.name.endswith(".raw"):
        content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d, format=(string)S16LE, channels=(int)1" %(args.rate/2)

    ws = MyClient(args.audiofile, args.uri + '?%s' % (urllib.urlencode([("content-type", content_type)])), byterate=args.rate,
                  save_adaptation_state_filename=args.save_adaptation_state, send_adaptation_state_filename=args.send_adaptation_state)
    ws.connect()
    result = ws.get_full_hyp()
    print result.encode('utf-8')

# python client.py -u ws://localhost:8080/client/ws/speech -r 32000 <testfile>.wav
if __name__ == "__main__":
    main()

import vlc
import sys
import subprocess
import os
import tty
import termios
from random import randint
import speech_recognition as sr
from statistics import mode, StatisticsError
import Microphone

# Set up
r = sr.Recognizer()
path = str(sys.argv[1])
songs = os.listdir(path)
numSongs = len(songs)
isEnd = False
state = 0 # 0 = ไม่มีเพลงเล่น, 1 = มีเพลงเล่น, 2 = มีเพลงเล่นแต่หยุด

# Random the first song to play
rnd = randint(0, numSongs - 1)
history = []; history.append(rnd)
now = 0
song = path + '/' + songs[history[now]]

player = vlc.MediaPlayer(song)

kor = "ขอ เพลง "
stop = "หยุด เล่น "
back = "กลับ "

print("Welcome to Dj Kaldi music player")
print("Press spacebar to a input command")

origin_settings = termios.tcgetattr(sys.stdin)

while True:
    tty.setraw(sys.stdin)
    x = 0
    while x != chr(32):
        x = sys.stdin.read(1)[0]
        if x == chr(27):
            isEnd = True
            break
    if isEnd:break
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, origin_settings)
    
    if state != 2: player.pause()

    Microphone.record()

    command = ''
    all_result = ['', '', '']
    for i in range(3):
        c = 0
        count_penalties = 0
        while True:
            result = subprocess.check_output(["/usr/local/opt/python/bin/python2.7", "client.py", "-u", "ws://localhost:8080/client/ws/speech", "-r", "32000", "microphone-results.wav"])
            if result: 
                print(result)
                trans = result.decode('utf-8').replace('\n', '').split('.')[0]
                if trans != '': 
                    c += 1
                    count_penalties = 0
                    break
                else:
                    count_penalties += 1
                    if count_penalties == 20:
                        break
            if count_penalties == 20:break
            if c == 4:break
        if c == 4 or count_penalties == 20:
            command = ''
            break

        all_result[i] = trans
        print(all_result)
        if all_result[1] == all_result[0]:
            command = all_result[0]
            break
        if all_result[2] != '' and (all_result[2] == all_result[1] or all_result[2] == all_result[0]):
            command = all_result[2]         

    if command != '':
        print("Perform task: " + command)
        if command == kor:
            if state == 0:
                player.play()
                state = 1

            elif state == 1:
                player.stop()
                next_rnd = randint(0, numSongs - 1)
                while(next_rnd == history[now]):
                    next_rnd = randint(0, numSongs - 1)
                history.append(next_rnd)
                now += 1

                song = path + '/' + songs[history[now]]
                player = vlc.MediaPlayer(song)
                player.play()

            elif state == 2:
                player.play()
                state = 1

        elif command == stop:
            print("pause the song")
            state = 2

        elif command == back:
            if now != 0:
                print("back to the previous song")
                player.stop()
                player = vlc.MediaPlayer(path + '/' + songs[history[now - 1]])
                history = history[:now]
                now -= 1
                player.play()
            else:
                print("There is no previous song")
                player.play()
                state = 1
        else:
            print("Not recognized as 1 of the commands or not sure, Please try again")
            if state == 1: player.play()
    else:
        print("Please try again")
        if state == 1: player.play()
        
termios.tcsetattr(sys.stdin, termios.TCSADRAIN, origin_settings)