import socket
import time
import cv2
import numpy
import sys

from threading import Thread
from queue import Queue
from config import Config
from packer import Packer


class Piece(object):
    def __init__(self, idx, ctime, frame):
        self.idx = idx
        self.ctime = ctime
        self.frame = frame

    def __lt__(self, other):
        return self.ctime > other.ctime


class VideoStreamHR:
    def __init__(self, queue_size=128):
        self.stopped = False

        self.config = Config()
        self.packer = Packer()
        self.initConfig()
        # self.Q = PriorityQueue(maxsize=self.queue_size)
        self.Q = Queue(maxsize=self.queue_size)
        self.img_Q = Queue(maxsize=self.queue_size)

        self.piece_array = []
        self.piece_time = int(time.time() * 1000)
        self.piece_fps = 40
        for i in range(self.packer.frame_pieces):
            self.piece_array.append(None)

        # init timestamp
        self.frame = numpy.zeros(self.packer.frame_size_3d, dtype=numpy.uint8)
        self.imshow = self.frame.reshape(self.packer.h, self.packer.w, self.packer.d)
        self.last_frame_time = int(time.time() * 1000)
        self.require = True
        self.time_delay = 0
        self.delay_timer = int(time.time() * 1000)
        self.receive_fps = 0
        self.info_pack = None

    def initConfig(self):
        # Initialize size information
        config = self.config
        # Initialize connection information
        host = config.getConfig("server", "host")
        port = config.getConfig("server", "port")
        feed_host = config.getConfig("server", "feed_host")
        feed_port = config.getConfig("server", "feed_port")
        self.address = (host, int(port))
        self.feed_address = (feed_host, int(feed_port))

        # Initialize the package header information
        self.head_name = config.getConfig("header", "name")
        self.head_data_len_len = int(config.getConfig("header", "data"))
        self.head_index_len = int(config.getConfig("header", "index"))
        self.head_time_len = int(config.getConfig("header", "time"))

        # Initialize queue size information
        self.queue_size = int(config.getConfig("receive", "queue_size"))

    def initConnectionSock(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(self.address)
            return sock
        except socket.error as msg:
            print(msg)
            sys.exit(1)

    def initConnection(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(self.address)
        except socket.error as msg:
            print(msg)
            sys.exit(1)

    def closeConnection(self):
        self.sock.close()

    def start(self):
        # start threads to recieve
        for i in range(self.packer.frame_pieces - 8):
            # intialize thread
            thread = Thread(target=self.recvThread, args=(i,))
            thread.daemon = True

            thread.start()

        decode_thread = Thread(target=self.rebuildThread, args=(i,))
        decode_thread.daemon = True
        decode_thread.start()

        send_thread = Thread(target=self.sendThread, args=())
        send_thread.daemon = True
        send_thread.start()

        return self

    def stop(self):
        # indicate that the thread should be stopped
        self.stopped = True
        # wait until stream resources are released (producer thread might be still grabbing frame)
        self.thread.join()

    def sendThread(self):
        print("Try to connect...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(self.feed_address)
        print("Connection Established Successful!")
        last_send = int(time.time() * 1000)
        while True:
            if self.info_pack is None: continue
            cnow = int(time.time() * 1000)
            if cnow - last_send > 500:
                s.sendall(self.info_pack)
                last_send = int(time.time() * 1000)
            pass
        s.close()
        return

    def recvThread(self, thread_idx):
        sock = self.initConnectionSock()

        stopped = False
        while True:
            if stopped: break
            # otherwise, ensure the queue has room in it
            if not self.Q.full():
                try:
                    data, addr = sock.recvfrom(self.packer.pack_len)
                    idx, ctime, raw_img = self.packer.unpackData(data)

                    line_data = numpy.frombuffer(raw_img, dtype=numpy.uint8)
                    line_data = cv2.imdecode(line_data, 1).flatten()
                    # add the frame to the queue
                    self.Q.put(Piece(idx, ctime, line_data))

                except:
                    pass
            else:
                time.sleep(0.01)  # Rest for 10ms, we have a full queue

    def rebuildThread(self, idx):
        while True:
            # flow control
            if self.Q.qsize() > self.packer.piece_limit:
                self.Q = Queue()
                if self.Q.mutex:
                    self.Q.queue.clear()
            try:
                avg_time = 0
                pack = self.Q.get()
                pack_num = 1

                avg_time = ptime = pack.ctime
                loop = self.packer.frame_pieces - 1
                while (pack is not None) and (loop >= 0):
                    idx = pack.idx
                    data = pack.frame

                    row_start = idx * self.packer.piece_size
                    row_end = (idx + 1) * self.packer.piece_size
                    self.frame[row_start:row_end] = data
                    if self.Q.qsize() == 0:
                        break
                    pack = self.Q.get()
                    loop -= 1
                self.img_Q.put(self.frame.reshape(self.packer.h, self.packer.w, self.packer.d))
                ctime = int(time.time() * 1000)
                self.time_delay = ctime - ptime

                self.info_pack = self.packer.packInfoData(self.receive_fps, ptime)
            except:
                pass
        return

    def running(self):
        return self.more() or not self.stopped

    def read(self):
        frame = self.Q.get()
        return frame
        if self.Q.qsize() > self.queue_size * 0.2:  # self.queue_size*0.1
            self.Q = Queue()
            if self.Q.mutex:
                self.Q.queue.clear()
        return frame
        # Flow control
        now = int(time.time() * 1000)
        if self.Q.qsize() == 0:
            return None

        while self.Q.qsize() > 0:
            frame = self.Q.get()
            ctime = frame.ctime
            # select only when frametime is later than previous frame
            if ctime >= self.last_frame_time:
                self.last_frame_time = ctime
                break

        if self.Q.qsize() > self.queue_size * 0.1:  # self.queue_size*0.1
            self.Q = Queue()
            if self.Q.mutex:
                self.Q.queue.clear()
        return frame

    def readImg(self):
        if self.img_Q.qsize() == 0:
            return None
        frame = self.img_Q.get()
        # flow control
        if self.img_Q.qsize() > self.packer.frame_limit:  # self.queue_size*0.1
            self.img_Q = Queue()
            if self.img_Q.mutex:
                self.img_Q.queue.clear()
        return frame

    def readShow(self):
        nvs = self.start()
        last_frame_time = time.time()
        tshow, fshow = 0, 0
        while True:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            now = time.time()
            frame = self.readImg()
            if frame is not None:

                # fps showing
                cnow = int(time.time() * 1000)
                if now - last_frame_time > 0:
                    nvs.receive_fps = int(1.0 / (now - last_frame_time))
                if cnow - nvs.delay_timer > 200:
                    nvs.delay_timer = cnow
                    tshow = nvs.time_delay
                    fshow = nvs.receive_fps

                # record time of last frame
                last_frame_time = time.time()

                cv2.imshow("Receive server", frame)

    def more(self):
        # return True if there are still frames in the queue. If stream is not stopped, try to wait a moment
        tries = 0
        while self.Q.qsize() == 0 and not self.stopped and tries < 5:
            time.sleep(0.1)
            tries += 1

        return self.Q.qsize() > 0


def ReceiveServer():
    t = 0
    if t == 0:
        VideoStreamHR().readShow()  # One-time use
    elif t == 1:
        con = Config()
        host = con.getConfig("server", "host")
        port = con.getConfig("server", "port")
        address = (host, int(port))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(address)
        bfsize = 46080
        chuncksize = 46081
        frame = numpy.zeros(bfsize * 20, dtype=numpy.uint8)
        cnt = 0
        while True:
            cnt += 1
            data, addr = sock.recvfrom(chuncksize)
            i = int.from_bytes(data[-1:], byteorder='big')
            line_data = numpy.frombuffer(data[:-1], dtype=numpy.uint8)
            frame[i * 46080:(i + 1) * 46080] = line_data
            if cnt == 20:
                cv2.imshow("frame", frame.reshape(480, 640, 3))
                cnt = 0

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    else:
        print("Unex")
        nvs = VideoStreamHR().start()
        frame = numpy.zeros(nvs.packer.frame_size_3d, dtype=numpy.uint8)
        cnt = 0
        while nvs.more():
            cnt += 1
            pack = nvs.read()
            if pack is not None:
                idx = pack.idx
                data = pack.frame
                row_start = idx * nvs.packer.piece_size
                row_end = (idx + 1) * nvs.packer.piece_size
                frame[row_start:row_end] = data
                if cnt == nvs.packer.frame_pieces:
                    cv2.imshow("FireStreamer", frame.reshape(nvs.packer.h, nvs.packer.w, nvs.packer.d))
                    cnt = 0
                nvs.require = True

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    print("Server is quitting! ")
    cv2.destroyAllWindows()


if __name__ == '__main__':
    ReceiveServer()