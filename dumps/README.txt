Put your own M-One flash dump here (512 KB .bin), made with: python tools/mone.py COMx jdump dumps/m1_flash.bin
Dump twice and compare. Then: python tools/build_app.py dumps/m1_flash.bin -> dumps/app.lst
.bin and .lst files are never committed (.gitignore): this repo holds no TC Electronic data.
