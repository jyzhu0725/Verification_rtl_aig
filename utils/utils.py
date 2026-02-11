import numpy as np 
import os 
import shlex
import subprocess
import time

def run_command(command, timeout=-1):
    start_time = time.time()
    process = os.popen(command)
    stdout = process.read()
    process.close()
    return stdout, time.time() - start_time