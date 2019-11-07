# HRVS
V1
1. Background
High-resolution real-time video transmission based on UDP protocol: Play video or capture the camera image from one computer to another computer in the same LAN. Try to make the video as high as possible while ensuring the highest possible resolution. Caton.
  1.1 Transfer video
The transmission video can take the form of a picture or a stream, and the project takes the form of transmitting pictures, and displays multiple pictures within 1 s through the visual persistence effect to form a continuous video picture.
  1.2 Test resources:
Laptop's  camera (720p)
"007: Spectra" (Bluray@720p)
Alien: Contract (Bluray@1080p).

2. Function realization
  2.1 TCP/IP protocol
The basis of video transmission is the UDP transport protocol, which is an important type in the TCP/IP protocol.
  2.2 Flow Control Flow Control
The ACK command sent by the receiving end to the transmitting end controls the transmission process of the transmitting end, thereby ensuring the effect of the video playback at the receiving end (the ACK information of the receiving end is sent based on the TCP protocol)

3. Solution overview
  3.1 Program Infrastructure
Use Python's Socket to capture the video of the camera using Opencv.
  3.2 Block processing
Since the original captured image is large, even if it is directly compressed into the jpg format, its size is too large. UDP can only transmit a data area of ​​65535 bytes in size. Therefore, it is necessary to block and number the pictures, and compress the image data after the blocks into a jpg format.
  3.3 Multi-threaded reception
Used by the receiving end, each thread is a socket, and the received data is stored in the data slice pool.
  3.4 Grab the data pool
Another thread on the receiving end, used to repeatedly read the data slice from the data slice pool, and update the screen according to the number of the data slice (the screen is an array dedicated to image display). The updated results are temporarily stored in the image pool
  3.5 display
The main thread of the receiving end repeatedly reads the picture from the picture pool and displays it.

4. Technical details
4.1 Transport Protocol
4.2 Blocking algorithm  
4.3 JPG compression
4.4 Receive Queue
