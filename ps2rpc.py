import socket
import time
import subprocess
import logging
import pathlib
import os
import sys
from dotenv import load_dotenv 
from pypresence import Presence

# TODO Kill RPC after disconnect in OPL

load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
HOST_IP = os.getenv('HOST_IP')
PS2_IP = os.getenv('PS2_IP')

PATH = pathlib.Path.cwd()
GAMEDB_PATH = PATH / 'GameDB.txt'

DVD_FILTER = bytes.fromhex('5c004400560044005c')
GAMES_BIN_FILTER = bytes.fromhex('5c004400560044005c00670061006d00650073002e00620069006e')

PING_GRACE = 3
GameDB = {}


# poor man's python
def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text  # or whatever


def load_gamename_map(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file.readlines():
            code, name = line.rstrip().split(":", 1)  # this splits the line into 2 parts on the first colon
            GameDB[code] = name  # this adds a new key/value to the dictionary


def ping_ps2(ip=PS2_IP):
    # Define the ping command based on the operating system
    # ping_cmd = ["ping", "-c", "1", ip]  # For Linux/macOS
    ping_cmd = ["ping", "-n", "1", ip, "-w", "5000"]  # For Windows
    try:
        # Execute the ping command and capture the output
        result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=5)
        output = result.stdout.lower()
        # Check the output for successful ping
        if "ttl=" in output:
            logging.debug("PS2 is alive")
            return True
        else:
            return False
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        logging.exception(f"An error occurred: {e}")
        return False


def main():
    logger.info(f"---------------------------------")
    logger.info(f"PS2 IP is set as {PS2_IP}")
    logger.info(f"Host IP is set as {HOST_IP}")
    load_gamename_map(GAMEDB_PATH)
    logger.info(f"GameDB: loaded {len(GameDB)} game(s)")
    RPC = Presence(CLIENT_ID)  # Initialize the client class
    RPC.connect()  # Start the handshake loop
    # create a raw socket and bind it to the public interface
    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
    s.bind((HOST_IP, 0))
    # Include IP headers
    s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    # receive all packets
    s.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
    PS2Online = False
    while True:
        message, address = s.recvfrom(65565)
        ip, port = address
        if ip == PS2_IP:
            if not PS2Online:
                RPC.update(state="Idle",
                           details="running OPL",
                           large_image="https://i.imgur.com/HjuVXhR.png", 
                           #https://i.imgur.com/MXzehWn.png for OPL logo
                           large_text="Open PS2 Loader",
                           start=time.time())
                logger.info("PS2 has come online")
                PS2Online = True
            # drop last byte
            msg_slice = message[128:-1]
            if msg_slice.startswith(GAMES_BIN_FILTER):
                continue
            elif msg_slice.startswith(DVD_FILTER):
                gamepath = bytes([c for c in msg_slice if c != 0x00]).decode()
                gamecode, gamename, _ = remove_prefix(gamepath, "\\DVD\\").rsplit(
                    ".", 2
                )
                fixed_gamecode = gamecode.replace('_', '-').replace('.', '')
                fixed_gamename = GameDB[fixed_gamecode]
                RPC.update(
                    state=fixed_gamecode,  # middle text
                    details=fixed_gamename,  # top text
                    large_image=f"https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/{fixed_gamecode}.jpg",
                    large_text=fixed_gamename,  # large image hover text
                    small_image="https://i.imgur.com/91Nj3w0.png",
                    small_text="PlayStation 2",  # small image hover text
                    start=time.time(),  # timer
                )
                logger.info("RPC started: " + gamecode + " - " + fixed_gamename)
                time.sleep(10)  # necessary wait to avoid dropped pings on game startup
                ping_count = 1
                ping_lost = False
                while ping_count <= PING_GRACE:
                    if ping_ps2(PS2_IP):
                        ping_count = 1
                        if ping_lost:
                            logging.info("PS2 has resumed pings")
                            ping_lost = False
                            # wait before pinging again
                        time.sleep(3)
                    else:
                        logging.warning(f"No response from PS2,. ({ping_count}/{PING_GRACE} attempts)")
                        ping_lost = True
                        ping_count += 1
                PS2Online = False
                RPC.clear()
                logging.info("PS2 has gone offline, RPC terminated")
                # we don't talk about bruno
                time.sleep(3)
                s.recvfrom(65565)
                s.recvfrom(65565)
                s.recvfrom(65565)
                s.recvfrom(65565)
                s.recvfrom(65565)
                time.sleep(3)
    # receive a packet
    # disabled promiscuous mode
    s.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)

if __name__ == "__main__":
    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler('logs.log')
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)s: %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.INFO,
        handlers=[stream_handler,file_handler]
    )
    logger = logging.getLogger()
    try:
        main()
    except Exception as e:
        logger.exception(e)
        input()
