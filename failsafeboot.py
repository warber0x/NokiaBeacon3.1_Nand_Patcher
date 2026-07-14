#!/usr/bin/env python3

#######################################################
# Auto boot : Start the router from UART
# Requirement: 
# - Patch the firmware using my scipt in this folder
# - Flash your nand
# - Having a shell in the router through UART
# !!! I'm not responsible if you break your device !!! 
#######################################################

import serial
import sys
import time
import argparse

parser = argparse.ArgumentParser(description="Nokia Beacon 3.1 — Failsafe Auto Exploit")
parser.add_argument("device", nargs="?", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
parser.add_argument("-b", "--baud", type=int, default=115200, help="Baud rate (default: 115200)")
args = parser.parse_args()

DEV = args.device
BAUD = args.baud

SCRIPT = r"""
#!/bin/sh
# Nokia Beacon 3.1 booting up the system and activate secboot.
# Unfortunately this should be done at each restart since the squashFS is signed
# Before running this script you should flash the firmware (Working on upgrading this using the UI)

# Mount and activate serial in case of reboot
mount_root
fw_setenv secboot 1

# Ticky part:
# - it loads drivers
# - start bridge, virtual interfaces and the the chip nic0
# - start the interfaces

ubusd &
/etc/init.d/platform start
/etc/init.d/diagshell start

insmod /lib/modules/5.10.161/hcfg-core.ko
insmod /lib/modules/5.10.161/phyadpt.ko
/etc/init.d/rtk_base start

ip link add dev ecd0 type veth peer name ecd1
ip link set ecd0 up
ip link set ecd1 up
ifconfig nic0 up
sleep 1

# All good ? turn on the interface
ifconfig eth0 up
ifconfig eth1 up
ifconfig eth2 up
ifconfig eth3 up

brctl addbr br-lan
brctl addif br-lan ecd0
brctl addif br-lan nic0

ifconfig ecd0 0.0.0.0 up
ifconfig br-lan 192.168.18.1 netmask 255.255.255.0 up

# Mount an overlay filesystem
mkdir -p /tmp/ov_upper /tmp/ov_work
mount -t overlay overlay -o lowerdir=/,upperdir=/tmp/ov_upper,workdir=/tmp/ov_work /mnt

# Disable root password for our ssh
sed -i 's|^root:[^:]*|root:|' /mnt/etc/passwd
sed -i 's|^root:[^:]*|root:|' /mnt/etc/shadow

mount --bind /mnt/etc/passwd /etc/passwd
mount --bind /mnt/etc/shadow /etc/shadow

# Create dropbear keys
dropbearkey -t rsa -f /tmp/dk_rsa
dropbearkey -t ed25519 -f /tmp/dk_ed

# Create a script that will be executed once the router is ready
printf '#!/bin/sh\nsleep 150\nkillall dropbear\nsleep 2\ndropbear -r /tmp/dk_rsa -r /tmp/dk_ed -p 0.0.0.0:22 -p 0.0.0.0:2222 -B\nfw_setenv secboot 1\necho "[*] All good ! try to connect to 192.168.18.1 :)"' > /tmp/fix_ssh.sh

# run and wait for the script
chmod +x /tmp/fix_ssh.sh
/tmp/fix_ssh.sh &

# Start the webserver
/webs/thttpd -dd /webs/ -p 80 &

# disable quagga shell blocking our terminal
mount --bind /dev/null /etc/rc.d/S60quagga
mount --bind /dev/null /etc/rc.d/S50syslog-ng
mount --bind /dev/null /etc/rc.d/S50cron

# Disable failsafe and allow the kernel to boot
touch /tmp/sysupgrade
kill $(cat /tmp/.failsafe)
"""

BANNER = """
+--------------------------------------------------+
|  Nokia Beacon 3.1 -- Auto Boot      							|
|  UART -> Failsafe -> Root Shell -> SSH Access    |
+--------------------------------------------------+
"""

def log(prefix, msg):
    print(f"  {prefix} {msg}")

def wait_for(s, text, timeout=120):
    buf = b""
    start = time.time()
    while time.time() - start < timeout:
        data = s.read(s.in_waiting or 1)
        if data:
            buf += data
            if text.encode() in buf:
                return True
    return False

def wait_for_any_output(s, timeout=300):
    spin = ["/", "-", "\\", "|"]
    i = 0
    start = time.time()
    while time.time() - start < timeout:
        if s.in_waiting:
            return True
        elapsed = int(time.time() - start)
        print(f"\r  [/] Waiting for serial output... {spin[i % 4]} ({elapsed}s)", end="", flush=True)
        i += 1
        time.sleep(0.5)
    print()
    return False

print(BANNER)
log("[*]", f"Connecting to {DEV} @ {BAUD} baud...")

try:
    s = serial.Serial(DEV, BAUD, timeout=1)
except Exception as e:
    log("[!]", f"Failed to open {DEV}: {e}")
    sys.exit(1)

log("[*]", "Serial connected!")
print()

# Stage 1: Check if shell is already available, or wait for device activity
log("[*]", "Stage 1: Checking if device is alive...")
log("[*]", "Sending Enter to check for existing shell...")

s.reset_input_buffer()
s.write(b"\r\n")
time.sleep(2)
data = s.read(s.in_waiting or 4096)
if data:
    text = data.decode("utf-8", errors="replace")
    if "/ #" in text or "# " in text:
        log("[*]", "Device is already on with a shell!")
    else:
        log("[*]", "Device is on -- got serial output!")
        log("[*]", "Waiting 30 seconds before probing...")
        time.sleep(30)
else:
    log("[*]", "No response -- waiting for device to power on...")
    if wait_for_any_output(s, timeout=300):
        print()
        log("[*]", "Activity detected on serial!")
        log("[*]", "Waiting 30 seconds before probing...")
        time.sleep(30)
    else:
        print()
        log("[!]", "No activity for 5 minutes -- is the device powered on?")
        s.close()
        sys.exit(1)

print()

# Stage 2: Press Enter every 5 seconds, look for shell
log("[*]", "Stage 2: Probing for shell...")
log("[*]", "Pressing Enter every 5 seconds, looking for '/ #'...")

shell_found = False
start = time.time()
attempt = 0
while time.time() - start < 120:
    attempt += 1
    s.reset_input_buffer()
    s.write(b"\r\n")
    time.sleep(5)
    data = s.read(s.in_waiting or 4096)
    if not data:
        print(f"\r  [/] Attempt {attempt}: no response, waiting...", end="", flush=True)
        continue
    text = data.decode("utf-8", errors="replace")
    if "/ #" in text or "# " in text:
        print()
        log("[*]", "Got prompt -- verifying with 'id'...")
        s.reset_input_buffer()
        s.write(b"id\n")
        time.sleep(2)
        data = s.read(s.in_waiting or 4096)
        text = data.decode("utf-8", errors="replace")
        if "uid=" in text:
            shell_found = True
            log("[*]", f"Shell confirmed! ({text.strip().split(chr(10))[-1].strip()})")
            break
        else:
            log("[!]", "Got prompt but 'id' failed -- retrying...")
    else:
        print(f"\r  [/] Attempt {attempt}: got output but no shell prompt yet...", end="", flush=True)

if not shell_found:
    print()

if shell_found:
    print()

    # Stage 3: Send exec /sbin/init
    log("[*]", "Stage 3: Starting init...")
    log("[*]", "Sending: exec /sbin/init")
    s.reset_input_buffer()
    s.write(b"exec /sbin/init\n")
    time.sleep(2)
else:
    log("[*]", "No shell found -- device may be already booting...")

print()

# Stage 4: Wait for failsafe prompt and send f
log("[*]", "Stage 4: Waiting for failsafe prompt...")
log("[*]", "Watching for 'to enter failsafe mode'...")

if wait_for(s, "to enter failsafe mode", timeout=120):
    log("[*]", "Failsafe prompt detected!")
    log("[*]", "Sending 'f'...")
    s.write(b"f\n")
else:
    log("[!]", "Failsafe prompt not detected within 120s")
    log("[!]", "Try power cycling the router and run again")
    s.close()
    sys.exit(1)

print()

# Stage 5: Wait for "- failsafe -" confirmation then verify shell
log("[*]", "Stage 5: Waiting for failsafe confirmation...")

if wait_for(s, "- failsafe -", timeout=30):
    log("[*]", "Failsafe mode confirmed!")
else:
    log("[!]", "No '- failsafe -' seen -- trying anyway...")

log("[*]", "Pressing Enter to get shell...")
shell_ready = False
for attempt in range(10):
    s.reset_input_buffer()
    s.write(b"\r\n")
    time.sleep(3)
    data = s.read(s.in_waiting or 4096)
    text = data.decode("utf-8", errors="replace")
    if "root@" in text or "/ #" in text or "# " in text:
        log("[*]", "Got prompt -- verifying with 'id'...")
        s.reset_input_buffer()
        s.write(b"id\n")
        time.sleep(2)
        data = s.read(s.in_waiting or 4096)
        text = data.decode("utf-8", errors="replace")
        if "uid=" in text:
            shell_ready = True
            log("[*]", "Failsafe shell confirmed!")
            break
    print(f"\r  [/] Attempt {attempt + 1}: waiting for shell...", end="", flush=True)

print()
if not shell_ready:
    log("[!]", "No shell after failsafe -- aborting")
    s.close()
    sys.exit(1)

print()

# Stage 6: Inject exploit script
log("[*]", "Stage 6: Injecting exploit script...")
print()

lines = [l for l in SCRIPT.strip().split("\n") if l.strip() and not l.strip().startswith("#")]
for line in lines:
    s.write(line.encode() + b"\n")
    time.sleep(0.5)

time.sleep(3)
log("[*]", "Script injected!")
print()

# Stage 7: Wait for boot confirmation
log("[*]", "Stage 7: Waiting for boot to start...")

if wait_for(s, "procd", timeout=30):
    log("[*]", "procd started -- full boot in progress!")
else:
    log("[!]", "procd not detected but script was sent -- continuing...")

print()
log("[*]", "All done! Boot is running.")
log("[*]", "Wait for 5 minutes before any attempts")
log("[*]", "ssh-keygen -R 192.168.18.1")
log("[*]", "After 5 min: execute ssh-keygen -R 192.168.18.1 && ssh root@192.168.18.1")
log("[*]", "Happy hacking Hax0r!")

s.close()
