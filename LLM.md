# LLM Interaction Guide for mtapy

This document provides guidance for AI assistants (like me) and developers on how to interact with, modify, and extend the `mtapy` codebase.

## Background

互传联盟（Mutual Transmission Alliance, MTA）是由小米、OPPO和vivo于2019年成立的，旨在实现跨品牌设备之间的快速文件传输。目前android已加入的有：小米、OPPO、vivo、联想、realme、努比亚、海信、魅族、一加、坚果、黑鲨、中兴、ROG、华硕、三星、荣耀

mtapy is a Python implementation of MTA, based on the CatShare project. CatShare is also a third-party implementation

## Source code goals

- keep the source code simple, easy to understand
- will be used as a lib, so later can be published on pypi
- struct the code in sans-io manner, use `asyncio` as the default transport
- leave the crypto, ble, wifi direct part as pluggable under `drivers` folder for various OS
- target macOS in this version. Extendable to Win/Linux later
-  Do not introduce too many third party libs.  `bleak` and `websockets` are acceptable.
- use `python` for testing, not `python3` as it points to system one on my local Mac.
- prefer let-it-crash during development stage, don't be overly protective with excessive try-except.
- make a `demo.py`.  macOS scan for BLE devices and show the logs (make logs be compact), the device connect to the macOS and transfer a file.
