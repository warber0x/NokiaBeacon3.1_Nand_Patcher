# Nokia Beacon 3.1 — UART Enable & Root Shell Firmware Patcher

## NAND Partition Layout

| Partition | Offset     | Size      | Description              |
| --------- | ---------- | --------- | ------------------------ |
| boot      | 0x00000000 | 4M        | Bootloader               |
| env       | 0x00400000 | 1M        | Environment variables    |
| env2      | 0x00500000 | 1M        | Backup environment       |
| RI        | 0x00600000 | 1536K     | Runtime information      |
| binfo     | 0x00800000 | 2M        | Board information        |
| image0    | 0x00A00000 | 70M       | Primary firmware image   |
| image1    | 0x05000000 | 70M       | Secondary firmware image |
| cfg       | 0x09600000 | 20M       | Configuration storage    |
| cfg_bak   | 0x0AA00000 | 20M       | Configuration backup     |
| log       | 0x0BE00000 | 15M       | Logs                     |
| extfs     | 0x0CD00000 | 5M        | Extended filesystem      |
| bbt       | 0x0D200000 | 2M        | Bad block table          |
| data      | 0x0D400000 | Remaining | User / runtime data      |

---

## Description

This tool patches a raw NAND firmware dump from the Nokia Beacon 3.1 router to:

* Enable UART serial console
* Disable secure boot console restriction
* Inject `init=/bin/sh` into boot arguments
* Spawn a root shell during boot

The patch operates directly on the redundant U-Boot environment partitions (`env` and `env2`) while preserving NAND page layout and OOB data.

---

## How the Script Works

### 1. Firmware Validation

The script verifies that the firmware matches the expected format by checking for a known header signature inside the first environment block:

* Skips CRC (4 bytes)
* Skips flag (1 byte)
* Confirms presence of `active_bank=`

This ensures the firmware belongs to the Nokia Beacon 3.1 layout.

---

### 2. Removing OOB and Extracting ENV

NAND layout:

```
[ 2048 bytes data | 128 bytes OOB ]
```

The script:

* Iterates through each NAND page
* Extracts only the 2048-byte data portion
* Removes OOB
* Reconstructs a clean 1MB environment buffer

This is done for:

* ENV1 (primary)
* ENV2 (redundant)

---

### 3. Prevent Double Patching

The script checks for:

```
init=/bin/sh
```

If already present, it stops to avoid corrupting the firmware.

---

### 4. Enable UART (secboot patch)

Search:

```
secboot=
```

Patch:

```
secboot=1
```

This forces the bootloader to allow serial console interaction.

The modification is applied to both ENV partitions.

---

### 5. Inject Root Shell

Original bootargs:

```
setenv more_args ubi.mtd=${ubi_mtd} root=${root_mtd} rootfstype=squashfs
```

Patched bootargs:

```
setenv more_args ubi.mtd=${ubi_mtd} root=${root_mtd} rootfstype=squashfs init=/bin/sh
```

This spawns a root shell instead of launching the normal init system.

---

### 6. CRC Recalculation

Environment format:

```
[ CRC32 | FLAG | DATA ... ]
```

CRC is calculated over:

```
DATA only (excluding CRC and flag)
```

Python logic:

```
crc = binascii.crc32(newEnv[5:]) & 0xFFFFFFFF
```

The new CRC is written into:

```
offset 0x0 – 0x3
```

Both ENV partitions receive the updated CRC.

---

### 7. Rebuilding NAND Image

The script reconstructs firmware by:

1. Writing original data before ENV
2. Writing patched ENV1 pages
3. Re-inserting original OOB bytes
4. Writing patched ENV2 pages
5. Re-inserting original OOB bytes
6. Appending remaining NAND data unchanged

This preserves:

* ECC data
* bad block markers
* page alignment

---

## Result After Boot

After flashing patched firmware:

* UART console enabled
* Secure boot console restriction disabled
* Boot process interrupted
* Root shell spawned
* Full root access available

---

## Usage

```
python patcher.py -i OriginalDump.bin
```

Optional output file:

```
python patcher.py -i OriginalDump.bin -o patched.bin
```

---

## Warning

* Do NOT patch already patched firmware
* Always keep original NAND dump
* Flashing incorrect image may brick device
* Use at your own risk

---

## Author

TheRed0ne
https://thered0ne.com
