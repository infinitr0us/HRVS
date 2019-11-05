from threading import Thread
import socket
import cv2
import numpy
import time
import sys
import os

from config import Config
from packer import Packer


class WebVideoStream:

    def __init__(self, src="test.mp4"):
        self.config = Config()
        self.packer = Packer()
        # initialize the file video stream along with the boolean
        # used to indicate if the thread should be stopped or not
        os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
        os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 15]
        self.stream = cv2.VideoCapture(0)

        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.packer.w)  # float
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.packer.h)  # float
        self.stopped = False

        self.requesting = False
        self.request = False
        self.quit = False

        self.fps = 40
        self.recv_fps = 0
        self.push_sleep = 0.01
        self.push_sleep_min = 0.001
        self.push_sleep_max = 0.2

        self.send_sleep = 0.05
        self.send_sleep_min = 0.01
        self.send_sleep_max = 0.1

        self.network_delay = 0
        self.delay_timer = int(time.time() * 1000)

        self.piece_array = []
        self.piece_time = int(time.time() * 1000)
        self.piece_fps = 40
        for i in range(self.packer.frame_pieces):
            self.piece_array.append(None)

        self.frame = numpy.zeros(self.packer.frame_size_3d, dtype=numpy.uint8)
        self.imshow = self.frame.reshape(self.packer.h, self.packer.w, self.packer.d)
        self.frame_size = 0
        self.piece_size = 0
        self.frame_pieces = 0
        self.init_config()
        self.init_connection()

        # intialize thread and lock
        self.thread = Thread(target=self.update, args=())
        self.thread.daemon = True

    def init_config(self):
        config = self.config
        # initialization
        host = config.get("server", "host")
        port = config.get("server", "port")
        feed_host = config.get("server", "feed_host")
        feed_port = config.get("server", "feed_port")
        self.address = (host, int(port))
        self.feed_address = (feed_host, int(feed_port))

        # initialize delay info
        self.frame_delay = float(config.get("delay", "frame"))
        self.piece_delay = float(config.get("delay", "piece"))

        # Initialize queue size information
        self.queue_size = int(config.get("receive", "queue_size"))

    def init_connection(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self.sock.bind(self.address)
        except socket.error as msg:
            print(msg)
            sys.exit(1)

    def close_connection(self):
        self.sock.close()

    def start(self):
        # start a thread to read frames from the file video stream
        self.thread.start()

        recv_thread = Thread(target=self.recv_thread, args=())
        recv_thread.daemon = True
        recv_thread.start()

        return self

    def update(self):
        piece_size = self.packer.piece_size
        # keep looping infinitely until the thread is stopped
        while True:
            # if the thread indicator variable is set, stop the thread
            if self.stopped:
                return

            time.sleep(self.push_sleep)
            # otherwise, read the next frame from the stream
            (grabbed, frame_raw) = self.stream.read()

            now = int(time.time() * 1000)
            for i in range(self.packer.frame_pieces):
                self.packer.pack_data(i, now, frame_raw, self.piece_array, self.piece_time, self.piece_fps)

        return

    def Q_flow_control(self):
        if self.piece_fps == 0: return False  # Zero means no change yet
        if self.piece_fps > self.packer.send_fps:
            self.push_sleep = min(self.push_sleep + 0.01, self.push_sleep_max)
            return True
        if self.piece_fps < self.packer.send_fps:
            self.push_sleep = max(self.push_sleep - 0.01, self.push_sleep_min)
        return False

    def send_flow_control(self):
        if self.recv_fps == 0: return False
        if self.recv_fps > self.packer.recv_fps_limit:
            self.send_sleep = min(self.send_sleep + 0.01, self.send_sleep_max)
            return True
        if self.recv_fps < self.packer.recv_fps_limit:
            self.send_sleep = max(self.send_sleep - 0.01, self.send_sleep_min)
        return False

    def get_request(self):
        if self.requesting: return

        print("waiting...")
        thread = Thread(target=self.get_request_thread, args=())
        thread.daemon = True
        thread.start()
        self.requesting = True

    def get_request_thread(self):
        while True:
            data = b''
            try:
                data, address = self.sock.recvfrom(4)
            except:
                pass
            if (data == b"get"):
                self.request = True
                break
            elif (data == b"quit"):
                self.quit = True
                break

    def read(self, i):
        return self.piece_array[i]

    def read_send(self, i):

        pack = self.piece_array[i]
        if pack is None: return
        self.sock.sendto(pack, self.address)


    def send_thread(self, i):
        pack = self.piece_array[i]
        if pack is None: return
        self.sock.sendto(pack, self.address)

    def recv_thread(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(self.feed_address)
        s.listen(1)
        conn, addr = s.accept()
        while True:
            data = conn.recv(self.packer.info_pack_len)
            if len(data) > 0:
                sname, server_fps, send_ctime = self.packer.unpack_info_data(data)
                now = int(time.time() * 1000)
                self.network_delay = int((now - send_ctime) / 2.0)
                self.recv_fps = server_fps
        conn.close()

    def stop(self):
        # indicate that the thread should be stopped
        self.stopped = True


def SendVideo():
    t = 0
    if t == 0:
        wvs = WebVideoStream().start()
        sock = wvs.sock
        address = wvs.address

        running = True
        while running:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                running = False
                continue

            now = time.time()
            wvs.send_flow_control()
            time.sleep(wvs.send_sleep)
            for i in range(wvs.packer.frame_pieces):
                wvs.read_send(i)
            now1 = time.time()
            cnow = int(now1 * 1000)
            ctime = now1 - now
            if ctime > 0:
                send_fps = str(int(1.0 / ctime)).ljust(4)
                recv_fps = str(wvs.recv_fps).ljust(4)
                net_delay = str(wvs.network_delay).ljust(4)

                if cnow - wvs.delay_timer > 300:
                    wvs.delay_timer = cnow

                    img = numpy.zeros((80, 700, 3), numpy.uint8)
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    bottomLeftCornerOfText = (10, 50)
                    fontScale = 0.7
                    fontColor = (255, 255, 255)
                    lineType = 2
                    cv2.putText(img,
                                'Hello World! Send FPS:' + send_fps + ", Recv FPS:" + recv_fps + ", Net delay:" + net_delay,
                                bottomLeftCornerOfText,
                                font,
                                fontScale,
                                fontColor,
                                lineType)
                    cv2.imshow("Send Client", img)



    else:
        con = Config()
        host = con.get("server", "host")
        port = con.get("server", "port")
        address = (host, int(port))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        capture = cv2.VideoCapture(0)
        capture.set(cv2.CAP_PROP_MODE, cv2.CAP_MODE_YUYV)
        # Read one frame of image, read successfully: ret=1 frame= one frame of image read; read failure: ret=0
        ret, frame = capture.read()
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]

        while True:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            # Stopping 0.1S prevents the processing of sending too fast service. However, if the server handles a lot, you should increase this value.
            time.sleep(0.01)
            ret, frame = capture.read()
            frame = cv2.flip(frame, 1)  # horizontal flip
            result, imgencode = cv2.imencode('.jpg', frame, encode_param)
            print(len(imgencode))
            s = frame.flatten().tostring()

            for i in range(20):
                time.sleep(0.001)
                sock.sendto(s[i * 46080:(i + 1) * 46080] + i.to_bytes(1, byteorder='big'), address)


    exit(0)



if __name__ == '__main__':
    SendVideo()
