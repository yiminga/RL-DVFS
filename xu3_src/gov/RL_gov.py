import sysfs_paths_xu3 as sfs
import devfreq_utils_xu3 as dvfs
from state_space_params_xu3 import *
import perf_module as pm
import numpy as np
import multiprocessing as mp
import subprocess, os
import ctypes
import time


# Array of global state-action values. Dimensions are:
# (num vf settings for big cluster * num state variables * max num buckets )
Q = np.zeros( (FREQS, VARS, BUCKETS) ) 


def checkpoint_statespace():
	return None

def load_statespace():
	return None

# XU3 has built-in sensors, so use them:
def get_power():
	# Just return big cluster power:
	return dvfs.getPowerComponents()[0]

def reward1(counters, temps, power):
	# Return sum of IPC minus sum of thermal violations:
	total_ipc = counters[c4ipc] + counters[c5ipc] + counters[c6ipc] + counters[c7ipc]
	thermal_v = np.array(temps) - THERMAL_LIMIT
	thermal_v = np.maximum(thermal_v, 0.0)
	thermal_t = np.sum(thermal_v)
	reward = total_ipc - (thermal_v * RHO)
	return reward

def init_RL():
	# Make sure perf counter module is loaded
	process = subprocess.Popen(['lsmod'], stdout=subprocess.PIPE)
	output, err = process.communicate()
	loaded = "perf_counters" in output
	if not loaded:
		print("WARNING: perf-counters module not loaded. Loading...")
		process = subprocess.Popen(['sudo', 'insmod', 'perf-counters.ko'])
		output, err = process.communicate()
	profile_statespace() 

	print("FINISHED")
	return

def get_counter_value(cpu_num, attr_name):
	with open("/sys/kernel/performance_counters/cpu{}/{}".format(cpu_num, attr_name), 
				'r') as f:
		val = float(f.readline().strip())
	return val

def set_period(p):
	for cpu_num in range(4,8):
		with open("/sys/kernel/performance_counters/cpu{}/sample_period_ms".format(cpu_num), 
				'w') as f:
			f.write("{}\n".format(p))


'''
Returns state figures, non-quantized.
Includes branch misses, IPC, and L2 misses per instruction for each core, plus big cluster power.
TODO: add leakage power
'''
def get_raw_state():	
	# Get the change in counter values:
	diffs = np.zeros((4,4))
	P = get_power()

	for cpu in range(4,8):
		diffs[cpu-4, 0] = get_counter_value(cpu, "branch_mispredictions")
		diffs[cpu-4, 1] = get_counter_value(cpu, "cycles")
		diffs[cpu-4, 2] = get_counter_value(cpu, "instructions_retired")
		diffs[cpu-4, 3] = get_counter_value(cpu, "data_memory_accesses")

	T = [float(x) for x in dvfs.getTemps()]

	# Multiply instructions by factor of 1000:
	diffs[:,2] *= 1000.0
	# Multiply cycles by factor of on million:
	diffs[:,1] *= 1000000.0
	# Compute state params from that:
	raw_state = [diffs[0,0]/diffs[0,2], diffs[0,2]/diffs[0,1], diffs[0,3]/diffs[0,2], T[0],\
				 diffs[1,0]/diffs[1,2], diffs[1,2]/diffs[1,1], diffs[1,3]/diffs[1,2], T[1],\
				 diffs[2,0]/diffs[2,2], diffs[2,2]/diffs[2,1], diffs[2,3]/diffs[2,2], T[2],\
				 diffs[3,0]/diffs[3,2], diffs[3,2]/diffs[3,1], diffs[3,3]/diffs[3,2], T[3],\
				 P]
	return raw_state


'''
Place state in 'bucket' given min/max values and number of buckets for each value
'''
def bucket_state(raw):
	# Use bucket width to determine index of each raw state value:
	all_mins = np.array([bmiss_MIN, ipc_MIN, mpi_MIN, temp_MIN]*4 + [pwr_MIN])
	all_widths = np.array([bmiss_width, ipc_width, mpi_width, temp_width]*4 + [pwr_width])
	raw_floored = np.array(raw) - all_mins
	state = np.divide(raw_floored, all_widths)
	return state


def profile_statespace():
	ms_period = int(PERIOD*1000)
	set_period(ms_period)
	try:
		max_state = np.load('max_state_{}ms.npy'.format(ms_period))
		min_state = np.load('min_state_{}ms.npy'.format(ms_period))
	except:
		max_state = get_raw_state()
		min_state = max_state
	i = 0
	while True:
		start = time.time()
		raw = get_raw_state()
		max_state = np.maximum.reduce([max_state, raw])
		min_state = np.minimum.reduce([min_state, raw])
		i += 1
		if i % 100 == 0:
			np.save('max_state_{}ms.npy'.format(ms_period), max_state)
			np.save('min_state_{}ms.npy'.format(ms_period), min_state)
			print("{}: Checkpointed raw state max and min.".format(i))
			print(raw)
		end = time.time()
		time.sleep((float(ms_period)/1000) - (end-start))


def Q_learning(states):
	return


if __name__ == "__main__":
	init_RL()
