import vlc
import sys
import subprocess
import os
import tty
import termios
from random import randint
import speech_recognition as sr
import statistics 

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
	
	with sr.Microphone(sample_rate = 16000) as source:
		print('\nListening. . .')
		audio = r.listen(source)

	try:
		with open("microphone-results.wav", "wb") as f:
			f.write(audio.get_wav_data())
		
		# Find what the command was ?
		command = ''
		all_result = ['', '', '']
		for i in range(3):
			while True:
				result = subprocess.check_output(["/usr/local/opt/python/bin/python2.7", "client.py", "-u", "ws://localhost:8080/client/ws/speech", "-r", "32000", "microphone-results.wav"])
				if result: 
					trans = result.decode('utf-8').replace('\n', '')
					if len(trans) != 0: break
			all_result[i] = trans
			if i > 0:
				try:
					if mode(all_result[0:(i+1)]) != '':
						command = statistics.mode(all_result).split('.')[0]
				except statistics.StatisticsError:
					command = all_result[2].split('.')[0]
				break

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

	except sr.RequestError as e:
  		print("Could not understand audio, continue playing. . .")
  		player.play()
  		
termios.tcsetattr(sys.stdin, termios.TCSADRAIN, origin_settings)