import cv2

from config import Config
from threading import Thread


class Packer:

    def __init__(self):

        # Compress parameter, Default=95
        self.encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        self.info_pack_len = 16
        self.initConfig()

    def initConfig(self):

        config = Config()

        # initialize camera info
        self.w = w = int(config.getConfig("camera", "w"))
        self.h = h = int(config.getConfig("camera", "h"))
        self.d = d = int(config.getConfig("camera", "d"))
        self.frame_pieces = frame_pieces = int(config.getConfig("camera", "pieces"))
        self.frame_size = w * h
        self.frame_size_3d = w * h * d
        self.piece_size = int(w * h * d / frame_pieces)
        self.idx_frame = int(h / self.frame_pieces)  # Lines of orginal image occupy

        # Initialize the package header information
        self.head_name = config.getConfig("header", "name")
        self.head_data_len_len = int(config.getConfig("header", "data"))
        self.head_index_len = int(config.getConfig("header", "index"))
        self.head_time_len = int(config.getConfig("header", "time"))
        self.img_len = int(config.getConfig("header", "data_size"))
        self.pack_len = int(config.getConfig("header", "total_size"))

        # Under the current coding,head_len=16
        self.head_len = len(self.head_name) + self.head_data_len_len + self.head_index_len + self.head_time_len

        # Initialize queue size information
        self.queue_size = int(config.getConfig("receive", "queue_size"))
        self.frame_limit = int(config.getConfig("receive", "frame_limit"))
        self.piece_limit = int(config.getConfig("receive", "piece_limit"))
        self.farme_delay = float(config.getConfig("receive", "frame_delay"))

        self.queue_size = int(config.getConfig("send", "queue_size"))
        self.send_piece_limit = int(config.getConfig("send", "piece_limit"))
        self.send_piece_min = int(config.getConfig("send", "piece_min"))
        self.send_fps = int(config.getConfig("send", "fps"))
        self.recv_fps_limit = int(config.getConfig("send", "recv_fps"))

    def packData(self, index, create_time, data, piece_array, piece_time, piece_fps):
        """
        Pack data over udp
        """
        if len(data) == 0:
            return None
        # intialize compress thread
        thread = Thread(target=self.compress, args=(index, create_time, data, piece_array, piece_time, piece_fps))
        thread.daemon = True
        thread.start()

    def unpackData(self, res):
        data_len = 0
        index = -1
        create_time = 0
        data = b''
        if len(res) < self.head_len:
            return index, create_time, data
        head_block = res[:self.head_len]
        name, data_len, index, create_time = self.unpackHeader(head_block)
        data_end = data_len + self.head_len
        body_block = res[self.head_len:data_end]

        return index, create_time, body_block

    def packHeader(self, data_len, index, create_time):
        res = b''
        res += self.head_name.encode()
        res += data_len.to_bytes(self.head_data_len_len, byteorder="big")
        res += index.to_bytes(self.head_index_len, byteorder="big")
        res += create_time.to_bytes(self.head_time_len, byteorder="big")
        return res

    def unpackHeader(self, head_block):
        name = head_block[:4]
        data_len = int.from_bytes(head_block[4:8], byteorder='big')
        index = int.from_bytes(head_block[8:9], byteorder='big')
        create_time = int.from_bytes(head_block[9:self.head_len], byteorder='big')
        return name, data_len, index, create_time

    def packInfoData(self, fps, ctime):
        res = b''
        res += self.head_name.encode()
        res += fps.to_bytes(4, byteorder="big")
        res += ctime.to_bytes(8, byteorder="big")
        return res

    def unpackInfoData(self, block):
        name = block[:4]
        server_fps = int.from_bytes(block[4:8], byteorder='big')
        ctime = int.from_bytes(block[8:16], byteorder='big')
        return name, server_fps, ctime

    def readCompress(self):
        frame = self.Q.getConfig()
        return frame

    def compress(self, idx, create_time, frame_raw, piece_array, piece_time, piece_fps):
        if len(frame_raw) == 0: return
        # Slice subscript calculation
        row_start = idx * self.idx_frame
        row_end = (idx + 1) * self.idx_frame
        # Video fragment compression, idx corresponds to the serial number of the current fragment
        try:
            result, imgencode = cv2.imencode('.jpg',frame_raw[row_start:row_end], self.encode_param)
        except:
            return
        if result:
            imgbytes = imgencode.tobytes()
            data_len = len(imgbytes)
            res = self.packHeader(data_len, idx, create_time)
            res += imgbytes

            # Update
            piece_array[idx] = res
            #
            if create_time - piece_time != 0:
                piece_fps = self.caculateFps(create_time - piece_time)
            piece_time = create_time
        return 1

    def caculateFps(self, ptime):
        return int(1000 / (ptime * 1.0))

    def setJpgQuality(self, quality):
        self.encode_param[1] = quality