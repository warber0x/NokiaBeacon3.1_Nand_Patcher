"""
================================================================================
 Nokia Beacon 3.1 Firmware Patcher – Enable UART + Root Shell
================================================================================
Author: TheRed0ne - https://thered0ne.com | Date: 2026-03-20

Description: Patches firmware to activate UART serial console and spawn root shell.
			 This is useful if you want to do some dynamic reverse engineering, vulnerability 
			 research or to know how it does work.

			 CRC = Page - 5bytes (CRC + flag) - OOB (128 bytes)

WARNING: 
Don't patch firmware already patched.
I'm not responsible for bricks or damage.
================================================================================
"""

import struct
import binascii
from  datetime import datetime
import argparse
import os
import sys

ENV1_OFFSET = 0x440000
ENV2_OFFSET = 0x550000
BOTTOM_DATA_OFFSET = 0x660000
ENV_SIZE = 0x100000
PAGE = 2048
OOB_SIZE= 128
PAGE_SIZE = PAGE + OOB_SIZE
CRC_SIZE = 4
FLAG_SIZE = 1
HEADER_SIGNATURE = "active_bank="

# Find and inject a shell in booting process
BOOTARGS = b"setenv more_args ubi.mtd=${ubi_mtd} root=${root_mtd} rootfstype=squashfs"
BOOTARGS_PATCH = BOOTARGS + b" init=/bin/sh"
BOOTARGS_PATCH_STR = b"init=/bin/sh"

# Find secboot and activate serial
SECBOOT= b'secboot=' # To activate serial output/input
SECBOOT_FLAG = b'1' # Activate UART
SECBOOT_ACTIVATION = SECBOOT + SECBOOT_FLAG

# Remove Serial_is_dis=1
SERIAL_IS_DIS = b'serial_is_dis=1'
SERIAL_IS_DIS_OFFSET_ENV1 = 0x0044014D
SERIAL_IS_DIS_OFFSET_ENV2 = 0x0055014D

BANNER = r"""
██████╗ ███████╗ █████╗  ██████╗ ██████╗ ███╗   ██╗    ██████╗  █████╗ ██╗  ██╗███████╗██████╗ 
██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗████╗  ██║    ██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗
██████╔╝█████╗  ███████║██║     ██║   ██║██╔██╗ ██║    ██████╔╝███████║█████╔╝ █████╗  ██████╔╝
██╔══██╗██╔══╝  ██╔══██║██║     ██║   ██║██║╚██╗██║    ██╔══██╗██╔══██║██╔═██╗ ██╔══╝  ██╔══██╗
██████╔╝███████╗██║  ██║╚██████╗╚██████╔╝██║ ╚████║    ██████╔╝██║  ██║██║  ██╗███████╗██║  ██║
╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝                                                                                       
for NokiaBeacon3.1 - Made by human brain, no AI ;)

"""

def CheckEnvHeader(offset):
	global raw
	signature = raw[offset + CRC_SIZE + FLAG_SIZE: offset + CRC_SIZE + FLAG_SIZE + len(HEADER_SIGNATURE)]
	if (signature == HEADER_SIGNATURE.encode('ascii')):
		print("[*] Valid Nokia Beacon 3.1 firmware")
		return True
	
	print ("[!] Invalid NokiaBeacon3.1 Firmware")
	return False
	
def GetENV(offset):
	global raw

	clean_env = bytearray()
	for i in range(ENV_SIZE // PAGE):
		address = offset + (i * PAGE_SIZE)
		clean_env.extend(raw[address: address + PAGE])

	return clean_env

def WriteNewFirmware(env1, env2, outputFile):
	global raw 

	data = bytearray()
	data.extend(raw[0: ENV1_OFFSET])

	for i in range (ENV_SIZE // PAGE): # 512
		localOffset = i * PAGE
		globalOffset = ENV1_OFFSET + (i * PAGE_SIZE)
		
		#print(f"0x{globalOffset:08X}") 
		data.extend(env1[localOffset : localOffset + PAGE])
		data.extend(raw[globalOffset + PAGE: globalOffset + PAGE + OOB_SIZE])

	for i in range (ENV_SIZE // PAGE): # 512
		localOffset = i * PAGE
		globalOffset = ENV2_OFFSET + (i * PAGE_SIZE)
		
		#print(f"0x{globalOffset:08X}") 
		data.extend(env2[localOffset : localOffset + PAGE])
		data.extend(raw[globalOffset + PAGE: globalOffset + PAGE + OOB_SIZE])

	data.extend(raw[BOTTOM_DATA_OFFSET:])

	with open(outputFile, "wb") as f:
		f.write(data)

def main():
	parser = argparse.ArgumentParser(
		description="A program to activate UART by disabling secboot, spawning a shell in the bootargs",
		epilog=f"Example: python {sys.argv[0]} -i OriginalDump.bin [-o OutputFileName.bin]"
	)

	parser.add_argument(
		"-i", "--input",
        type=str,
        help="Path to the Raw binary file"
	)

	parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file path (if not specified, prints only)"
    )

	args = parser.parse_args()

	if len(sys.argv) == 1:
		parser.print_help()
		sys.exit(1)

	if not os.path.isfile(args.input):
		parser.error(f"[-] Failed to open {args.input}!")

	print(BANNER)

	print("[*] Loading firmware...")
	global raw
	with open(args.input, "rb") as f:
		raw = bytearray(f.read())
	print(f"     => Loaded {len(raw)} bytes ({len(raw) / 1024 / 1024:.2f} MB)")

	print("[*] Validating firmware header...")
	if CheckEnvHeader(ENV1_OFFSET) == False:
		return

	print("[*] Extracting ENV partitions (removing OOB)...")
	env1 = GetENV(ENV1_OFFSET)
	env2 = GetENV(ENV2_OFFSET)
	print(f"     => ENV1: {len(env1)} bytes from offset 0x{ENV1_OFFSET:08X}")
	print(f"     => ENV2: {len(env2)} bytes from offset 0x{ENV2_OFFSET:08X}")

	print("[*] Checking the ENV partitions")
	if env1.find(BOOTARGS_PATCH_STR) > 0 or env2.find(BOOTARGS_PATCH_STR) > 0:
		print("[!] Quitting ! This firmware is already patched!")
		return

	print("[*] Patching secboot flag (UART activation)...")
	pos = env1.find(SECBOOT)
	env1[pos:pos+len(SECBOOT)+1] = SECBOOT_ACTIVATION
	print(f"     => ENV1: secboot=1 at offset 0x{pos:04X}")

	pos = env2.find(SECBOOT)
	env2[pos:pos+len(SECBOOT)+1] = SECBOOT_ACTIVATION
	print(f"     => ENV2: secboot=1 at offset 0x{pos:04X}")
 
	# print("[*] Removing serial_is_dis=1 flag...")
	# pos = env1.find(SERIAL_IS_DIS)
	# if (pos > 0):
	# 	end = env1.index(b'\x00', pos)
	# 	env1[pos-1:end] = b''
	# 	print(f"     => ENV1: Serial_is_dis at offset 0x{pos:04X}")

	# pos = env2.find(SERIAL_IS_DIS)
	# if (pos > 0):
	# 	end = env2.index(b'\x00', pos)
	# 	env2[pos-1:end] = b''
	# 	print(f"     => ENV2: Serial_is_dis at offset 0x{pos:04X}")

	print("[*] Injecting init=/bin/sh into bootargs...")
	pos = env1.find(BOOTARGS)
	newEnv1 = env1[:pos]
	newEnv1.extend(BOOTARGS_PATCH)
	newEnv1.extend(env1[pos+len(BOOTARGS):])
	# padding because len(SERIAL_IS_DIS) - len('init=/bin/sh') = 3 bytes to add to align the buffer
	#newEnv1 = newEnv1[:ENV_SIZE] + b'\x00\x00\x00'
	newEnv1 = newEnv1[:ENV_SIZE]
	print(f"     => ENV1: patched at offset 0x{pos:04X}")

	pos = env2.find(BOOTARGS)
	newEnv2 = env2[:pos]
	newEnv2.extend(BOOTARGS_PATCH)
	newEnv2.extend(env2[pos+len(BOOTARGS):])
	# padding because len(SERIAL_IS_DIS) - len('init=/bin/sh') = 3 bytes to add to align the buffer
	#newEnv2 = newEnv2[:ENV_SIZE] + b'\x00\x00\x00'
	newEnv2 = newEnv2[:ENV_SIZE]
	print(f"     => ENV2: patched at offset 0x{pos:04X}")

	
	print("[*] Recalculating CRC32 and writing firmware...")
	crc = binascii.crc32(newEnv1[5:]) & 0xFFFFFFFF # The CRC is calculated without the flag
	newEnv1[0:4] = struct.pack('<I', crc)
	newEnv2[0:4] = struct.pack('<I', crc)
	print(f"     => New CRC32: 0x{crc:08X}")

	now = datetime.now()
	defaultFileName = "PatchedFirmware_" + str(int(now.timestamp())) + ".bin"

	outputFile = args.output or defaultFileName
	WriteNewFirmware(newEnv1, newEnv2, outputFile)
	print("     => Written to patchedFirmware.bin")
	print("[*] Done! Firmware patched successfully.")

if __name__ == "__main__":
	main()

